"""
All DB operations live here. Routers and services never query directly.
"""
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import Client, ClientProfile, ClientCredentials, ClientSession, Vm, Cert, GrafanaAccess


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------

async def get_client_by_email(db: AsyncSession, email: str) -> Optional[Client]:
    result = await db.execute(select(Client).where(Client.email == email.lower()))
    return result.scalar_one_or_none()


async def get_client_by_slug(db: AsyncSession, slug: str) -> Optional[Client]:
    result = await db.execute(select(Client).where(Client.slug == slug))
    return result.scalar_one_or_none()


async def get_client_by_id(db: AsyncSession, client_id: bytes) -> Optional[Client]:
    result = await db.execute(select(Client).where(Client.id == client_id))
    return result.scalar_one_or_none()


async def create_client(db: AsyncSession, slug: str, company_name: str, account_type: str,
                        email: str, phone: Optional[str] = None) -> Client:
    client = Client(
        slug=slug,
        company_name=company_name,
        account_type=account_type,
        email=email.lower(),
        phone=phone,
    )
    db.add(client)
    await db.flush()  # populate server_default ID
    return client


async def update_client_status(db: AsyncSession, client_id: bytes, status: str,
                                error_message: Optional[str] = None):
    values = {"status": status, "updated_at": datetime.now(timezone.utc)}
    if error_message is not None:
        values["error_message"] = error_message
    await db.execute(update(Client).where(Client.id == client_id).values(**values))


# ---------------------------------------------------------------------------
# Client Profiles
# ---------------------------------------------------------------------------

async def create_client_profile(db: AsyncSession, client_id: bytes, **kwargs) -> ClientProfile:
    profile = ClientProfile(client_id=client_id, **kwargs)
    db.add(profile)
    await db.flush()
    return profile


async def get_client_profile(db: AsyncSession, client_id: bytes) -> Optional[ClientProfile]:
    result = await db.execute(select(ClientProfile).where(ClientProfile.client_id == client_id))
    return result.scalar_one_or_none()


async def update_onboarding_step(db: AsyncSession, client_id: bytes, step: int):
    await db.execute(
        update(ClientProfile)
        .where(ClientProfile.client_id == client_id)
        .values(onboarding_step=step)
    )


# ---------------------------------------------------------------------------
# Client Credentials
# ---------------------------------------------------------------------------

async def create_client_credentials(db: AsyncSession, client_id: bytes,
                                     password_hash: str) -> ClientCredentials:
    creds = ClientCredentials(client_id=client_id, password_hash=password_hash)
    db.add(creds)
    await db.flush()
    return creds


async def get_credentials(db: AsyncSession, client_id: bytes) -> Optional[ClientCredentials]:
    result = await db.execute(
        select(ClientCredentials).where(ClientCredentials.client_id == client_id)
    )
    return result.scalar_one_or_none()


async def increment_failed_attempts(db: AsyncSession, client_id: bytes):
    creds = await get_credentials(db, client_id)
    if creds:
        creds.failed_attempts = (creds.failed_attempts or 0) + 1
        await db.flush()


async def reset_failed_attempts(db: AsyncSession, client_id: bytes):
    await db.execute(
        update(ClientCredentials)
        .where(ClientCredentials.client_id == client_id)
        .values(failed_attempts=0, locked_until=None, last_login_at=datetime.now(timezone.utc))
    )


async def lock_account(db: AsyncSession, client_id: bytes, locked_until: datetime):
    await db.execute(
        update(ClientCredentials)
        .where(ClientCredentials.client_id == client_id)
        .values(locked_until=locked_until)
    )


async def set_reset_token(db: AsyncSession, client_id: bytes, token: str, expires: datetime):
    await db.execute(
        update(ClientCredentials)
        .where(ClientCredentials.client_id == client_id)
        .values(reset_token=token, reset_expires=expires)
    )


async def get_credentials_by_reset_token(db: AsyncSession, token: str) -> Optional[ClientCredentials]:
    result = await db.execute(
        select(ClientCredentials).where(ClientCredentials.reset_token == token)
    )
    return result.scalar_one_or_none()


async def update_password_hash(db: AsyncSession, client_id: bytes, new_hash: str):
    await db.execute(
        update(ClientCredentials)
        .where(ClientCredentials.client_id == client_id)
        .values(password_hash=new_hash, reset_token=None, reset_expires=None)
    )


# ---------------------------------------------------------------------------
# Client Sessions
# ---------------------------------------------------------------------------

async def create_session(db: AsyncSession, client_id: bytes, token_hash: str,
                          expires_at: datetime, user_agent: str = "", ip_address: str = "") -> ClientSession:
    session = ClientSession(
        client_id=client_id,
        token_hash=token_hash,
        expires_at=expires_at,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    db.add(session)
    await db.flush()
    return session


async def get_session_by_token_hash(db: AsyncSession, token_hash: str) -> Optional[ClientSession]:
    result = await db.execute(
        select(ClientSession).where(ClientSession.token_hash == token_hash)
    )
    return result.scalar_one_or_none()


async def invalidate_all_sessions(db: AsyncSession, client_id: bytes):
    now = datetime.now(timezone.utc)
    await db.execute(
        update(ClientSession)
        .where(ClientSession.client_id == client_id)
        .values(expires_at=now)
    )


# ---------------------------------------------------------------------------
# VMs
# ---------------------------------------------------------------------------

async def upsert_vm(db: AsyncSession, client_id: bytes, ip: str, hostname: str = "",
                    cloud: str = "unknown") -> Vm:
    result = await db.execute(
        select(Vm).where(Vm.client_id == client_id, Vm.ip == ip)
    )
    vm = result.scalar_one_or_none()
    if vm:
        vm.hostname = hostname
        vm.cloud = cloud
        vm.last_seen_at = datetime.now(timezone.utc)
    else:
        vm = Vm(client_id=client_id, ip=ip, hostname=hostname, cloud=cloud)
        db.add(vm)
    await db.flush()
    return vm


async def mark_node_exporter_installed(db: AsyncSession, vm_id: bytes):
    await db.execute(
        update(Vm).where(Vm.id == vm_id).values(has_node_exporter=1)
    )


async def get_client_vms(db: AsyncSession, client_id: bytes) -> list[Vm]:
    result = await db.execute(select(Vm).where(Vm.client_id == client_id))
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Certs
# ---------------------------------------------------------------------------

async def create_cert(db: AsyncSession, client_id: bytes, cert_serial: str, cert_pem: str,
                       fingerprint: str, expires_at: datetime) -> Cert:
    cert = Cert(
        client_id=client_id,
        cert_serial=cert_serial,
        cert_pem=cert_pem,
        fingerprint=fingerprint,
        expires_at=expires_at,
    )
    db.add(cert)
    await db.flush()
    return cert


async def get_active_cert_by_client(db: AsyncSession, client_id: bytes) -> Optional[Cert]:
    result = await db.execute(
        select(Cert).where(Cert.client_id == client_id, Cert.revoked == 0)
    )
    return result.scalar_one_or_none()


async def get_cert_by_fingerprint(db: AsyncSession, fingerprint: str) -> Optional[Cert]:
    result = await db.execute(
        select(Cert).where(Cert.fingerprint == fingerprint)
    )
    return result.scalar_one_or_none()


async def revoke_cert(db: AsyncSession, cert_id: bytes, revoked_by: str, reason: str):
    await db.execute(
        update(Cert)
        .where(Cert.id == cert_id)
        .values(revoked=1, revoked_at=datetime.now(timezone.utc),
                revoked_by=revoked_by, revoked_reason=reason)
    )


async def revoke_all_client_certs(db: AsyncSession, client_id: bytes, revoked_by: str, reason: str):
    await db.execute(
        update(Cert)
        .where(Cert.client_id == client_id, Cert.revoked == 0)
        .values(revoked=1, revoked_at=datetime.now(timezone.utc),
                revoked_by=revoked_by, revoked_reason=reason)
    )


async def update_cert_usage(db: AsyncSession, cert_id: bytes):
    result = await db.execute(select(Cert).where(Cert.id == cert_id))
    cert = result.scalar_one_or_none()
    if cert:
        cert.last_used_at = datetime.now(timezone.utc)
        cert.use_count = (cert.use_count or 0) + 1
        await db.flush()


# ---------------------------------------------------------------------------
# Grafana Access
# ---------------------------------------------------------------------------

async def create_grafana_access(db: AsyncSession, client_id: bytes, org_id: int,
                                 grafana_user: str, grafana_pass_encrypted: str,
                                 dashboard_uid: str, dashboard_url: str,
                                 laptop_dashboard_uid: str = "", laptop_dashboard_url: str = "") -> GrafanaAccess:
    ga = GrafanaAccess(
        client_id=client_id,
        org_id=org_id,
        grafana_user=grafana_user,
        grafana_pass=grafana_pass_encrypted,
        dashboard_uid=dashboard_uid,
        dashboard_url=dashboard_url,
        laptop_dashboard_uid=laptop_dashboard_uid,
        laptop_dashboard_url=laptop_dashboard_url,
    )
    db.add(ga)
    await db.flush()
    return ga


async def update_grafana_laptop_dashboard(db: AsyncSession, client_id: bytes,
                                           uid: str, url: str):
    await db.execute(
        update(GrafanaAccess)
        .where(GrafanaAccess.client_id == client_id)
        .values(laptop_dashboard_uid=uid, laptop_dashboard_url=url)
    )


async def get_grafana_access(db: AsyncSession, client_id: bytes) -> Optional[GrafanaAccess]:
    result = await db.execute(
        select(GrafanaAccess).where(GrafanaAccess.client_id == client_id)
    )
    return result.scalar_one_or_none()


async def update_grafana_pass(db: AsyncSession, client_id: bytes, encrypted_pass: str):
    await db.execute(
        update(GrafanaAccess)
        .where(GrafanaAccess.client_id == client_id)
        .values(grafana_pass=encrypted_pass)
    )
