"""
Standalone entry point for the WSS agent server.
Runs as a separate process/container so uvicorn hot-reload doesn't kill it.
"""
import asyncio
import logging
import os
import sys

# Add parent dir to path so local imports work when run directly as a script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.cert_authority import bootstrap_ca, bootstrap_server_cert, CA_CERT_PATH, SERVER_CERT_PATH  # noqa: E402
from core.agent_server import start_agent_server  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)


async def main():
    if not CA_CERT_PATH.exists():
        bootstrap_ca()
    if not SERVER_CERT_PATH.exists():
        bootstrap_server_cert()
    print("Starting WSS agent server…", flush=True)
    await start_agent_server()


if __name__ == "__main__":
    asyncio.run(main())
