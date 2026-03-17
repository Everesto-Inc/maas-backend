"""
Proxies Prometheus remote_write from laptop agents to our Prometheus.
Auth: Bearer JWT (same token embedded in the laptop docker command).
Prometheus remote_write sends snappy-compressed protobuf — we pass it through as-is.
"""
import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from db.models import Client
from services.auth_service import get_current_client
from config import settings

router = APIRouter(tags=["metrics"])


@router.post("/remote_write", status_code=204)
async def remote_write(
    request: Request,
    client: Client = Depends(get_current_client),
):
    body = await request.body()
    headers = {
        "Content-Type":                          request.headers.get("Content-Type", "application/x-protobuf"),
        "Content-Encoding":                      request.headers.get("Content-Encoding", "snappy"),
        "X-Prometheus-Remote-Write-Version":     "0.1.0",
    }
    async with aiohttp.ClientSession() as s:
        async with s.post(
            f"{settings.PROMETHEUS_URL}/api/v1/write",
            data=body,
            headers=headers,
        ) as r:
            if r.status not in (200, 204):
                text = await r.text()
                raise HTTPException(status_code=r.status, detail=text)
    return Response(status_code=204)
