"""
Full provisioning flow triggered when an agent first connects.
Status updates go to BOTH the DB and the SSE queue simultaneously.
"""
import asyncio
import secrets
import string
from typing import Optional
from db.database import AsyncSessionLocal
from db import crud
from core import vm_discoverer, prometheus_manager, grafana_client, error_classifier
from core.cert_authority import build_docker_command, issue_client_cert
from config import settings

# SSE queues per client slug — frontend subscribes to these
_sse_queues: dict[str, asyncio.Queue] = {}


def get_sse_queue(slug: str) -> asyncio.Queue:
    if slug not in _sse_queues:
        _sse_queues[slug] = asyncio.Queue()
    return _sse_queues[slug]


def drop_sse_queue(slug: str):
    _sse_queues.pop(slug, None)


async def _push(slug: str, db, client_id: bytes, event: str, message: str, detail: str = ""):
    """Update DB status AND push to SSE queue atomically."""
    await crud.update_client_status(db, client_id, event, detail or None)
    await db.commit()
    q = get_sse_queue(slug)
    await q.put({"event": event, "message": message, "detail": detail})


def _random_password(length: int = 20) -> str:
    chars = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(chars) for _ in range(length))


async def run_provisioning(slug: str, ws):
    async with AsyncSessionLocal() as db:
        client = await crud.get_client_by_slug(db, slug)
        if not client:
            return

        try:
            # Step 1 — Agent connected, start scanning
            await _push(slug, db, client.id, "scanning",
                        "Agent connected — scanning your VPC for VMs...")

            agent_ip = ws.remote_address[0]
            subnets  = await vm_discoverer.auto_detect_subnets(agent_ip)
            found_ips: list[str] = []
            for subnet in subnets:
                found_ips.extend(await vm_discoverer.scan_subnet(subnet))

            for ip in found_ips:
                await crud.upsert_vm(db, client.id, ip, cloud="unknown")
            await db.commit()

            await _push(slug, db, client.id, "installing",
                        f"Found {len(found_ips)} VM(s) — installing Node Exporter...")

            # Step 2 — Install Node Exporter on each VM
            ssh_key = "certs/agent_id_rsa"  # agent's private key for internal SSH
            installed: list[str] = []
            for ip in found_ips:
                ok = await vm_discoverer.install_node_exporter(ip, agent_ip, ssh_key)
                if ok:
                    installed.append(ip)
                    vm = await crud.upsert_vm(db, client.id, ip)
                    await crud.mark_node_exporter_installed(db, vm.id)
            await db.commit()

            # Step 3 — Prometheus targets
            await _push(slug, db, client.id, "provisioning",
                        "Configuring metrics collection...")
            prometheus_manager.write_targets(slug, installed)
            await prometheus_manager.reload_prometheus()

            # Step 4 — Grafana org + user + dashboard
            org_id = await grafana_client.create_org(f"{client.company_name} ({slug})")
            grafana_user = slug
            grafana_pass = _random_password()
            await grafana_client.create_org_user(org_id, grafana_user, grafana_pass, client.email)
            await grafana_client.ensure_prometheus_datasource(org_id)
            laptop_dash = await grafana_client.provision_laptop_dashboard(org_id)
            dash = await grafana_client.provision_dashboard(org_id, settings.NODE_EXPORTER_DASHBOARD_ID)

            # Encrypt grafana password before storing
            from services.encryption import encrypt
            await crud.create_grafana_access(
                db, client.id, org_id, grafana_user, encrypt(grafana_pass),
                dash["uid"], dash["url"],
                laptop_dash["uid"], laptop_dash["url"],
            )
            await db.commit()

            await _push(slug, db, client.id, "active",
                        "All set! Your dashboard is ready.", dash["url"])

        except Exception as exc:
            err = error_classifier.classify(exc)
            await _push(slug, db, client.id, "error", err.title, err.detail)
