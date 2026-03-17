"""
WSS hub that receives outbound agent connections.
Agents connect TO US — we never connect to them.

Each connected agent is stored in _tunnels keyed by client_slug.
"""
import ssl
import hashlib
import asyncio
import websockets
from db.database import AsyncSessionLocal
from db import crud
from core.orchestrator import run_provisioning

_tunnels: dict[str, websockets.WebSocketServerProtocol] = {}

CA_CERT_PATH   = "certs/ca/ca.crt"
SERVER_CERT    = "certs/server/server.crt"
SERVER_KEY     = "certs/server/server.key"
WS_PORT        = 8765
WS_CLOSE_REVOKED = 4403


def _cert_fingerprint(ws) -> str:
    der = ws.transport.get_extra_info("ssl_object").getpeercert(binary_form=True)
    return hashlib.sha256(der).hexdigest()


def _cert_cn(ws) -> str:
    cert = ws.transport.get_extra_info("ssl_object").getpeercert()
    for field in cert.get("subject", []):
        for k, v in field:
            if k == "commonName":
                return v
    return ""


async def handle_agent(ws):
    import logging
    logger = logging.getLogger("agent_server")
    fingerprint = _cert_fingerprint(ws)
    slug        = _cert_cn(ws)
    logger.info(f"Agent connected: slug={slug} fingerprint={fingerprint[:16]}…")

    async with AsyncSessionLocal() as db:
        cert = await crud.get_cert_by_fingerprint(db, fingerprint)
        if not cert or cert.revoked:
            logger.warning(f"Cert not found or revoked: {fingerprint[:16]}… revoked={getattr(cert,'revoked',None)}")
            await ws.close(WS_CLOSE_REVOKED, "Certificate revoked")
            return

        client = await crud.get_client_by_id(db, cert.client_id)
        if not client or client.status in ("disabled", "deprovisioned"):
            logger.warning(f"Client disabled: {slug} status={getattr(client,'status',None)}")
            await ws.close(WS_CLOSE_REVOKED, "Account disabled")
            return
        logger.info(f"Agent authenticated: {slug} client_status={client.status}")

        await crud.update_cert_usage(db, cert.id)

        if client.status == "pending":
            await crud.update_client_status(db, client.id, "connecting")

        await db.commit()

    _tunnels[slug] = ws

    try:
        if client.status in ("pending", "connecting"):
            asyncio.create_task(run_provisioning(slug, ws))

        # Keep connection alive — agent sends periodic pings
        async for _ in ws:
            pass
    finally:
        _tunnels.pop(slug, None)


async def force_disconnect(client_slug: str, reason: str = "revoked"):
    ws = _tunnels.get(client_slug)
    if ws:
        await ws.close(WS_CLOSE_REVOKED, reason)
        _tunnels.pop(client_slug, None)


async def start_agent_server():
    import logging
    logger = logging.getLogger("agent_server")
    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(SERVER_CERT, SERVER_KEY)
        ctx.load_verify_locations(CA_CERT_PATH)
        ctx.verify_mode = ssl.CERT_REQUIRED
        logger.info(f"Starting WSS agent server on port {WS_PORT}…")
        async with websockets.serve(handle_agent, "0.0.0.0", WS_PORT, ssl=ctx):
            logger.info(f"WSS agent server ready on :{WS_PORT}")
            await asyncio.Future()  # run forever
    except Exception as e:
        logger.error(f"WSS agent server failed: {e}", exc_info=True)
