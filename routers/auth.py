import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Union
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import get_db
from db import crud
from schemas.models import (
    IndividualSignupRequest, CompanySignupRequest,
    LoginRequest, PasswordResetRequest, PasswordResetConfirm,
    AuthResponse, ClientProfileOut,
)
from services.auth_service import hash_password, verify_password, create_access_token, hash_token
from services.email_service import send_welcome_email, send_password_reset_email

router = APIRouter(prefix="/auth", tags=["auth"])


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]", "-", name.lower().strip())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:50]


def _client_out(client, profile) -> ClientProfileOut:
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


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    body: Union[IndividualSignupRequest, CompanySignupRequest],
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    # Check email uniqueness
    existing = await crud.get_client_by_email(db, body.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered.")

    # Determine company name and slug
    if body.account_type == "individual":
        company_name = body.full_name
    else:
        company_name = body.company_name

    slug = _slugify(company_name)
    # Ensure slug uniqueness
    if await crud.get_client_by_slug(db, slug):
        slug = f"{slug}-{secrets.token_hex(3)}"

    # Create client
    client = await crud.create_client(
        db, slug=slug, company_name=company_name,
        account_type=body.account_type, email=body.email,
        phone=body.phone if hasattr(body, "phone") else None,
    )

    # Profile fields
    profile_kwargs = dict(
        full_name=body.full_name,
        country=body.country,
        timezone=body.timezone,
    )
    if body.account_type == "individual":
        pass
    else:
        profile_kwargs.update({
            k: v for k, v in dict(
                job_title=body.job_title,
                company_reg_no=body.company_reg_no,
                industry=body.industry,
                company_size=body.company_size,
                website=body.website,
                billing_address=body.billing_address,
                vat_number=body.vat_number,
            ).items() if v is not None
        })

    profile = await crud.create_client_profile(db, client.id, **profile_kwargs)
    await crud.create_client_credentials(db, client.id, hash_password(body.password))

    # Create session
    token = create_access_token(client.id.hex(), slug, client.plan)
    token_hash = hash_token(token)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    await crud.create_session(
        db, client.id, token_hash, expires_at,
        user_agent=request.headers.get("user-agent", ""),
        ip_address=request.client.host if request.client else "",
    )
    await db.commit()

    # Welcome email (non-blocking)
    try:
        await send_welcome_email(client.email, body.full_name, slug)
    except Exception:
        pass  # never fail signup because of email

    return AuthResponse(access_token=token, client=_client_out(client, profile))


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    client = await crud.get_client_by_email(db, body.email)
    if not client:
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    creds = await crud.get_credentials(db, client.id)
    if not creds:
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    # Account lockout check
    if creds.locked_until and creds.locked_until.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc):
        raise HTTPException(status_code=423, detail="Account locked. Try again later.")

    if not verify_password(body.password, creds.password_hash):
        await crud.increment_failed_attempts(db, client.id)
        if (creds.failed_attempts or 0) + 1 >= 5:
            locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
            await crud.lock_account(db, client.id, locked_until)
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    # Success
    await crud.reset_failed_attempts(db, client.id)

    if client.status == "disabled":
        await db.commit()
        raise HTTPException(status_code=403, detail="Account suspended.")

    token = create_access_token(client.id.hex(), client.slug, client.plan)
    token_hash = hash_token(token)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    await crud.create_session(
        db, client.id, token_hash, expires_at,
        user_agent=request.headers.get("user-agent", ""),
        ip_address=request.client.host if request.client else "",
    )
    await db.commit()

    profile = await crud.get_client_profile(db, client.id)
    return AuthResponse(access_token=token, client=_client_out(client, profile))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, db: AsyncSession = Depends(get_db)):
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token_hash = hash_token(auth.split(" ", 1)[1])
        session = await crud.get_session_by_token_hash(db, token_hash)
        if session:
            session.expires_at = datetime.now(timezone.utc)
            await db.commit()


@router.post("/reset-password")
async def request_reset(body: PasswordResetRequest, db: AsyncSession = Depends(get_db)):
    client = await crud.get_client_by_email(db, body.email)
    if client:
        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        await crud.set_reset_token(db, client.id, token, expires)
        await db.commit()
        try:
            await send_password_reset_email(client.email, token)
        except Exception:
            pass
    # Always return 200 to avoid email enumeration
    return {"message": "If that email exists, a reset link has been sent."}


@router.post("/reset-password/confirm")
async def confirm_reset(body: PasswordResetConfirm, db: AsyncSession = Depends(get_db)):
    creds = await crud.get_credentials_by_reset_token(db, body.token)
    if not creds:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token.")
    if creds.reset_expires and creds.reset_expires.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Reset token has expired.")

    await crud.update_password_hash(db, creds.client_id, hash_password(body.new_password))
    await crud.invalidate_all_sessions(db, creds.client_id)
    await db.commit()
    return {"message": "Password updated. Please log in."}
