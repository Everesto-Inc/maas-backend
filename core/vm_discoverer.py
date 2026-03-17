"""
Discover VMs in the client VPC by scanning the subnet for port 9100 (Node Exporter).
The agent VM acts as a gateway — it scans from inside the private subnet.
"""
import asyncio
import ipaddress
import socket
import paramiko

NODE_EXPORTER_PORT = 9100
SCAN_TIMEOUT = 1.0  # seconds per host


async def _port_open(ip: str, port: int) -> bool:
    loop = asyncio.get_event_loop()
    try:
        await asyncio.wait_for(
            loop.run_in_executor(None, _try_connect, ip, port),
            timeout=SCAN_TIMEOUT,
        )
        return True
    except (asyncio.TimeoutError, OSError):
        return False


def _try_connect(ip: str, port: int):
    with socket.create_connection((ip, port), timeout=SCAN_TIMEOUT):
        pass


async def scan_subnet(subnet: str) -> list[str]:
    """Return IPs in the subnet that have port 9100 open."""
    network = ipaddress.IPv4Network(subnet, strict=False)
    hosts = [str(h) for h in network.hosts()]
    tasks = [_port_open(ip, NODE_EXPORTER_PORT) for ip in hosts]
    results = await asyncio.gather(*tasks)
    return [ip for ip, open_ in zip(hosts, results) if open_]


async def auto_detect_subnets(agent_ip: str) -> list[str]:
    """Guess /24 subnet from agent IP."""
    parts = agent_ip.split(".")
    return [f"{'.'.join(parts[:3])}.0/24"]


async def install_node_exporter(target_ip: str, agent_ip: str, ssh_key_path: str) -> bool:
    """
    SSH from the agent VM into target_ip and install Node Exporter.
    Uses key-based auth — agent must have SSH access to all VMs in the VPC.
    """
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, _install_blocking, target_ip, ssh_key_path)
        return True
    except Exception:
        return False


def _install_blocking(target_ip: str, ssh_key_path: str):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(target_ip, username="ubuntu", key_filename=ssh_key_path, timeout=10)

    commands = [
        "sudo useradd -rs /bin/false node_exporter 2>/dev/null || true",
        "curl -sL https://github.com/prometheus/node_exporter/releases/download/v1.8.2/node_exporter-1.8.2.linux-amd64.tar.gz | sudo tar -xz -C /usr/local/bin --strip-components=1",
        "sudo tee /etc/systemd/system/node_exporter.service > /dev/null <<'EOF'\n[Unit]\nDescription=Node Exporter\n[Service]\nUser=node_exporter\nExecStart=/usr/local/bin/node_exporter\n[Install]\nWantedBy=multi-user.target\nEOF",
        "sudo systemctl daemon-reload && sudo systemctl enable --now node_exporter",
    ]
    for cmd in commands:
        _, stdout, stderr = ssh.exec_command(cmd)
        stdout.channel.recv_exit_status()
    ssh.close()
