import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import get_db
from db import crud
from db.models import Client
from config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer()

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_access_token(client_id_hex: str, slug: str, plan: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRE_HOURS)
    payload = {"sub": client_id_hex, "slug": slug, "plan": plan, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def create_laptop_agent_token(client_id_hex: str, slug: str, plan: str) -> tuple[str, datetime]:
    """30-day token for the laptop-agent docker command. Stored in CLIENT_SESSIONS."""
    expire = datetime.now(timezone.utc) + timedelta(days=30)
    payload = {"sub": client_id_hex, "slug": slug, "plan": plan,
               "token_type": "laptop_agent", "exp": expire}
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    return token, expire


async def get_current_client(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> Client:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        client_id_hex: Optional[str] = payload.get("sub")
        if not client_id_hex:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # Verify session is not revoked
    token_hash = hash_token(token)
    session = await crud.get_session_by_token_hash(db, token_hash)
    if not session or session.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")

    client_id = bytes.fromhex(client_id_hex)
    client = await crud.get_client_by_id(db, client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Client not found")

    if client.status == "disabled":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account suspended")
    if client.status == "deprovisioned":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account deprovisioned")

    return client


def check_plan_vm_limit(plan: str, current_vm_count: int):
    """Enforce VM limits per plan. Call before adding a new VM."""
    if plan == "free" and current_vm_count >= 3:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Free plan limited to 3 VMs. Upgrade to Pro for unlimited monitoring.",
        )
