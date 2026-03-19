import re
from typing import Optional, Literal
from pydantic import BaseModel, EmailStr, field_validator


PASSWORD_RE = re.compile(r'^(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z\d]).{8,}$')
PHONE_RE    = re.compile(r'^\+\d{7,15}$')


def validate_password(v: str) -> str:
    if not PASSWORD_RE.match(v):
        raise ValueError("min 8 chars, 1 uppercase, 1 number, 1 special character")
    return v


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class IndividualSignupRequest(BaseModel):
    account_type: Literal["individual"]
    full_name: str
    email: EmailStr
    password: str
    phone: Optional[str] = None
    country: str          # ISO 3166-1 alpha-2
    timezone: str

    @field_validator("password")
    @classmethod
    def strong_password(cls, v): return validate_password(v)

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, v): return v.lower()

    @field_validator("phone")
    @classmethod
    def e164_phone(cls, v):
        if v and not PHONE_RE.match(v):
            raise ValueError("Phone must be E.164 format, e.g. +1234567890")
        return v

    @field_validator("country")
    @classmethod
    def iso_country(cls, v):
        if len(v) != 2:
            raise ValueError("Country must be ISO 3166-1 alpha-2 code")
        return v.upper()


class CompanySignupRequest(BaseModel):
    account_type: Literal["company"]
    # Primary contact
    full_name: str
    job_title: Optional[str] = None
    email: EmailStr
    password: str
    phone: Optional[str] = None
    country: str
    timezone: str
    # Company details
    company_name: str
    company_reg_no: Optional[str] = None
    industry: Optional[str] = None
    company_size: Optional[str] = None
    website: Optional[str] = None
    billing_address: Optional[str] = None
    vat_number: Optional[str] = None

    @field_validator("password")
    @classmethod
    def strong_password(cls, v): return validate_password(v)

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, v): return v.lower()

    @field_validator("phone")
    @classmethod
    def e164_phone(cls, v):
        if v and not PHONE_RE.match(v):
            raise ValueError("Phone must be E.164 format, e.g. +1234567890")
        return v

    @field_validator("country")
    @classmethod
    def iso_country(cls, v):
        if len(v) != 2:
            raise ValueError("Country must be ISO 3166-1 alpha-2 code")
        return v.upper()

    @field_validator("company_name")
    @classmethod
    def company_name_length(cls, v):
        if len(v) < 2 or len(v) > 255:
            raise ValueError("Company name must be 2–255 characters")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, v): return v.lower()


class PasswordResetRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, v): return v.lower()


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def strong_password(cls, v): return validate_password(v)


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

class ClientProfileOut(BaseModel):
    slug: str
    company_name: str
    account_type: str
    email: str
    plan: str
    status: str
    full_name: Optional[str]
    country: Optional[str]
    timezone: Optional[str]

    class Config:
        from_attributes = True


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    client: ClientProfileOut


# ---------------------------------------------------------------------------
# Onboarding
# ---------------------------------------------------------------------------

class OnboardingRequest(BaseModel):
    # Which subnets to scan (optional — agent auto-detects if not provided)
    subnets: Optional[list[str]] = None


class OnboardStatusEvent(BaseModel):
    event: str    # connecting | scanning | installing | provisioning | done | error
    message: str
    detail: Optional[str] = None


# ---------------------------------------------------------------------------
# Client resources
# ---------------------------------------------------------------------------

class VmOut(BaseModel):
    ip: str
    hostname: Optional[str]
    cloud: Optional[str]
    has_node_exporter: bool
    discovered_at: Optional[str]

    class Config:
        from_attributes = True


class GrafanaUrlResponse(BaseModel):
    url: str
    grafana_user: str
    grafana_pass: str


class LaptopCmdResponse(BaseModel):
    docker_cmd: str                      # Linux command (--network host, internal node_exporter)
    macos_cmd: str                       # macOS command (host.docker.internal, brew node_exporter)
    laptop_dashboard_url: Optional[str]  # Grafana dashboard path — available immediately
    token_expires_at: str                # ISO datetime — regenerate after this date


class GrafanaPasswordChange(BaseModel):
    new_password: str

    @field_validator("new_password")
    @classmethod
    def strong_password(cls, v): return validate_password(v)
