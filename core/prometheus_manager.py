"""Manages per-client file_sd JSON files for Prometheus scrape targets."""
import json
import aiohttp
from pathlib import Path
from config import settings


def _sd_path(client_slug: str) -> Path:
    return Path(settings.PROMETHEUS_SD_DIR) / f"{client_slug}.json"


def write_targets(client_slug: str, vm_ips: list[str]):
    """Write/update the file_sd JSON for this client's VMs."""
    targets = [{"targets": [f"{ip}:9100"], "labels": {"client": client_slug}} for ip in vm_ips]
    _sd_path(client_slug).write_text(json.dumps(targets, indent=2))
    return targets


def remove_targets(client_slug: str):
    """Remove the file_sd JSON — stops Prometheus from scraping this client."""
    path = _sd_path(client_slug)
    if path.exists():
        path.unlink()


async def reload_prometheus():
    """Signal Prometheus to reload its config / file_sd."""
    async with aiohttp.ClientSession() as s:
        async with s.post(settings.PROMETHEUS_RELOAD_URL) as r:
            r.raise_for_status()
