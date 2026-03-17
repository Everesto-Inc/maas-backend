import asyncio
import base64
import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import get_db
from db import crud
from db.models import Client
from core.cert_authority import issue_client_cert, build_docker_command
from core.orchestrator import get_sse_queue, drop_sse_queue
from services.auth_service import get_current_client
from schemas.models import OnboardingRequest

router = APIRouter(prefix="/onboard", tags=["onboarding"])


@router.post("")
async def start_onboarding(
    body: OnboardingRequest,
    client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
):
    """
    Issue mTLS cert, return docker run command.
    Client pastes this on their VM — agent connects back and provisioning begins.
    """
    # Revoke any existing cert first (reissue scenario)
    existing = await crud.get_active_cert_by_client(db, client.id)
    if existing:
        await crud.revoke_cert(db, existing.id, revoked_by="system", reason="reissued")

    cert_data = issue_client_cert(client.slug)

    await crud.create_cert(
        db,
        client_id=client.id,
        cert_serial=cert_data["cert_serial"],
        cert_pem=cert_data["cert_pem"],
        fingerprint=cert_data["fingerprint"],
        expires_at=cert_data["expires_at"],
    )
    await crud.update_onboarding_step(db, client.id, 2)
    await db.commit()

    cert_b64 = base64.b64encode(cert_data["cert_pem"].encode()).decode()
    key_b64  = base64.b64encode(cert_data["key_pem"].encode()).decode()
    ca_b64   = base64.b64encode(cert_data["ca_pem"].encode()).decode()

    docker_cmd = build_docker_command(
        client.slug,
        cert_data["cert_pem"],
        cert_data["key_pem"],
        cert_data["ca_pem"],
    )
    return {
        "docker_command": docker_cmd,
        "slug": client.slug,
        "cert_b64": cert_b64,
        "key_b64":  key_b64,
        "ca_b64":   ca_b64,
    }


@router.get("/{slug}/stream")
async def status_stream(
    slug: str,
    client: Client = Depends(get_current_client),
):
    """SSE endpoint — frontend subscribes here to get live provisioning updates."""
    queue = get_sse_queue(slug)

    async def event_generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("event") in ("active", "error"):
                        break
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"  # keep connection alive
        finally:
            drop_sse_queue(slug)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
