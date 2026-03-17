"""
All connection/provisioning errors go through here.
Never return raw exceptions to the client.
"""
from dataclasses import dataclass


@dataclass
class ClassifiedError:
    title: str
    detail: str
    fix: str            # human-readable fix in English
    fix_cmd: str = ""   # optional shell command to fix


def classify(error: Exception) -> ClassifiedError:
    msg = str(error).lower()

    if "connection refused" in msg or "connect call failed" in msg:
        return ClassifiedError(
            title="Agent not reachable",
            detail="The monitoring agent could not connect to the platform.",
            fix="Make sure the Docker container is running and has outbound access on port 443.",
            fix_cmd="docker ps | grep monitor-agent",
        )
    if "certificate" in msg or "ssl" in msg or "tls" in msg:
        return ClassifiedError(
            title="Certificate error",
            detail="The agent's certificate was rejected.",
            fix="Re-run the docker command from your setup page to get a fresh certificate.",
        )
    if "timeout" in msg:
        return ClassifiedError(
            title="Connection timed out",
            detail="The agent took too long to connect.",
            fix="Check that outbound port 443 is not blocked by a firewall or security group.",
            fix_cmd="curl -v https://agent.everesto.live",
        )
    if "ssh" in msg or "authentication" in msg:
        return ClassifiedError(
            title="SSH authentication failed",
            detail="Could not SSH into a discovered VM to install Node Exporter.",
            fix="Ensure the agent VM has SSH access to other VMs in the VPC using key-based auth.",
        )
    if "permission" in msg or "sudo" in msg:
        return ClassifiedError(
            title="Permission denied",
            detail="Node Exporter installation failed due to insufficient permissions.",
            fix="Make sure the SSH user has passwordless sudo access on all VMs.",
            fix_cmd="echo 'your-user ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/monitoring",
        )

    return ClassifiedError(
        title="Unexpected error",
        detail=str(error),
        fix="Contact support at support@everesto.live with your client ID.",
    )
