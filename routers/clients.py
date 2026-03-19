import secrets
import string
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import get_db
from db import crud
from db.models import Client
from schemas.models import ClientProfileOut, VmOut, GrafanaUrlResponse, LaptopCmdResponse, GrafanaPasswordChange
from services.auth_service import get_current_client, create_laptop_agent_token, hash_token
from services.encryption import decrypt, encrypt
from core import grafana_client
from config import settings

router = APIRouter(prefix="/clients", tags=["clients"])


def _random_password(length: int = 20) -> str:
    chars = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(chars) for _ in range(length))


@router.get("/me", response_model=ClientProfileOut)
async def get_me(
    client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
):
    profile = await crud.get_client_profile(db, client.id)
    return ClientProfileOut(
        slug=client.slug,
        company_name=client.company_name,
        account_type=client.account_type,
        email=client.email,
        plan=client.plan,
        status=client.status,
        full_name=profile.full_name if profile else None,
        country=profile.country if profile else None,
        timezone=profile.timezone if profile else None,
    )


@router.get("/me/vms", response_model=list[VmOut])
async def get_my_vms(
    client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
):
    vms = await crud.get_client_vms(db, client.id)
    return [
        VmOut(
            ip=vm.ip,
            hostname=vm.hostname,
            cloud=vm.cloud,
            has_node_exporter=bool(vm.has_node_exporter),
            discovered_at=vm.discovered_at.isoformat() if vm.discovered_at else None,
        )
        for vm in vms
    ]


@router.get("/me/grafana-url", response_model=GrafanaUrlResponse)
async def get_grafana_url(
    client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
):
    ga = await crud.get_grafana_access(db, client.id)
    if not ga:
        raise HTTPException(status_code=404, detail="Dashboard not provisioned yet.")

    grafana_pass = decrypt(ga.grafana_pass)
    url = grafana_client.generate_dashboard_url(ga.org_id, ga.dashboard_uid)
    return GrafanaUrlResponse(url=url, grafana_user=ga.grafana_user, grafana_pass=grafana_pass)


@router.put("/me/grafana-password")
async def change_grafana_password(
    body: GrafanaPasswordChange,
    client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
):
    ga = await crud.get_grafana_access(db, client.id)
    if not ga:
        raise HTTPException(status_code=404, detail="Grafana not provisioned yet.")
    await grafana_client.update_user_password(ga.grafana_user, body.new_password)
    await crud.update_grafana_pass(db, client.id, encrypt(body.new_password))
    await db.commit()
    return {"ok": True}


@router.get("/me/laptop-cmd", response_model=LaptopCmdResponse)
async def get_laptop_cmd(
    client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the laptop docker run command.
    On first call: provisions the Grafana org + My Laptop dashboard immediately
    so the dashboard link is available right away — no VPC agent needed.
    Issues a 30-day token so the user only needs to regenerate monthly.
    """
    # ── Provision Grafana org + laptop dashboard on first call ──────────────
    ga = await crud.get_grafana_access(db, client.id)
    if not ga:
        grafana_user = client.slug
        grafana_pass = _random_password()
        org_id = await grafana_client.create_org(f"{client.company_name} ({client.slug})")
        await grafana_client.create_org_user(org_id, grafana_user, grafana_pass, client.email)
        await grafana_client.ensure_prometheus_datasource(org_id)
        laptop_dash = await grafana_client.provision_laptop_dashboard(org_id)
        ga = await crud.create_grafana_access(
            db, client.id, org_id, grafana_user, encrypt(grafana_pass),
            dashboard_uid="", dashboard_url="",
            laptop_dashboard_uid=laptop_dash["uid"],
            laptop_dashboard_url=laptop_dash["url"],
        )
        await db.commit()
    elif not ga.laptop_dashboard_uid:
        # Org exists (from VPC provisioning) but laptop dashboard not yet created
        await grafana_client.ensure_prometheus_datasource(ga.org_id)
        laptop_dash = await grafana_client.provision_laptop_dashboard(ga.org_id)
        await crud.update_grafana_laptop_dashboard(db, client.id,
                                                   laptop_dash["uid"], laptop_dash["url"])
        await db.commit()
        ga = await crud.get_grafana_access(db, client.id)

    # ── Issue 30-day agent token ─────────────────────────────────────────────
    client_id_hex = client.id.hex()
    token, expires_at = create_laptop_agent_token(client_id_hex, client.slug, client.plan)
    await crud.create_session(db, client.id, hash_token(token), expires_at,
                              user_agent="laptop-agent", ip_address="")
    await db.commit()

    # ── Build docker run commands (Linux + macOS variants) ──────────────────
    platform_url = settings.PLATFORM_PUBLIC_URL.rstrip("/")

    linux_cmd = (
        f"docker run -d --name laptop-monitor --restart always \\\n"
        f"  --network host \\\n"
        f"  -e PLATFORM_URL={platform_url} \\\n"
        f"  -e CLIENT_SLUG={client.slug} \\\n"
        f"  -e CLIENT_TOKEN={token} \\\n"
        f"  -e INSTANCE_NAME=my-laptop \\\n"
        f"  {settings.LAPTOP_AGENT_IMAGE}"
    )

    macos_cmd = (
        f"docker run -d --name laptop-monitor --restart always \\\n"
        f"  -e PLATFORM_URL={platform_url} \\\n"
        f"  -e CLIENT_SLUG={client.slug} \\\n"
        f"  -e CLIENT_TOKEN={token} \\\n"
        f"  -e INSTANCE_NAME=my-laptop \\\n"
        f"  -e NODE_EXPORTER_URL=host.docker.internal:9100 \\\n"
        f"  {settings.LAPTOP_AGENT_IMAGE}"
    )

    return LaptopCmdResponse(
        docker_cmd=linux_cmd,
        macos_cmd=macos_cmd,
        laptop_dashboard_url=ga.laptop_dashboard_url,
        token_expires_at=expires_at.isoformat(),
    )
