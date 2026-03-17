from sqlalchemy import (
    Column, String, DateTime, SmallInteger, Integer, Text, ForeignKey, text, Index
)
from sqlalchemy.dialects.oracle import RAW
from sqlalchemy.orm import relationship
from db.database import Base


class Client(Base):
    __tablename__ = "CLIENTS"

    id             = Column("ID",            RAW(16),      primary_key=True, server_default=text("SYS_GUID()"))
    slug           = Column("SLUG",          String(100),  unique=True, nullable=False)
    company_name   = Column("COMPANY_NAME",  String(255),  nullable=False)
    account_type   = Column("ACCOUNT_TYPE",  String(20),   nullable=False)   # individual | company
    email          = Column("EMAIL",         String(255),  unique=True, nullable=False)
    phone          = Column("PHONE",         String(30))
    plan           = Column("PLAN",          String(20),   server_default=text("'free'"))
    status         = Column("STATUS",        String(30),   server_default=text("'pending'"))
    error_message  = Column("ERROR_MESSAGE", String(1000))
    created_at     = Column("CREATED_AT",    DateTime,     server_default=text("CURRENT_TIMESTAMP"))
    updated_at     = Column("UPDATED_AT",    DateTime,     server_default=text("CURRENT_TIMESTAMP"))

    profile     = relationship("ClientProfile",     back_populates="client", uselist=False)
    credentials = relationship("ClientCredentials", back_populates="client", uselist=False)
    sessions    = relationship("ClientSession",     back_populates="client")
    vms         = relationship("Vm",                back_populates="client")
    certs       = relationship("Cert",              back_populates="client")
    grafana     = relationship("GrafanaAccess",     back_populates="client", uselist=False)


class ClientProfile(Base):
    __tablename__ = "CLIENT_PROFILES"

    id              = Column("ID",              RAW(16),     primary_key=True, server_default=text("SYS_GUID()"))
    client_id       = Column("CLIENT_ID",       RAW(16),     ForeignKey("CLIENTS.ID"), unique=True, nullable=False)
    full_name       = Column("FULL_NAME",       String(255))
    job_title       = Column("JOB_TITLE",       String(100))
    country         = Column("COUNTRY",         String(100))
    timezone        = Column("TIMEZONE",        String(50))
    company_reg_no  = Column("COMPANY_REG_NO",  String(100))
    industry        = Column("INDUSTRY",        String(100))
    company_size    = Column("COMPANY_SIZE",    String(30))
    website         = Column("WEBSITE",         String(255))
    billing_address = Column("BILLING_ADDRESS", String(500))
    vat_number      = Column("VAT_NUMBER",      String(50))
    onboarding_step = Column("ONBOARDING_STEP", SmallInteger, server_default=text("1"))
    created_at      = Column("CREATED_AT",      DateTime,    server_default=text("CURRENT_TIMESTAMP"))

    client = relationship("Client", back_populates="profile")


class ClientCredentials(Base):
    __tablename__ = "CLIENT_CREDENTIALS"

    id              = Column("ID",              RAW(16),     primary_key=True, server_default=text("SYS_GUID()"))
    client_id       = Column("CLIENT_ID",       RAW(16),     ForeignKey("CLIENTS.ID"), unique=True, nullable=False)
    password_hash   = Column("PASSWORD_HASH",   String(255), nullable=False)
    reset_token     = Column("RESET_TOKEN",     String(255))
    reset_expires   = Column("RESET_EXPIRES",   DateTime)
    last_login_at   = Column("LAST_LOGIN_AT",   DateTime)
    failed_attempts = Column("FAILED_ATTEMPTS", SmallInteger, server_default=text("0"))
    locked_until    = Column("LOCKED_UNTIL",    DateTime)

    client = relationship("Client", back_populates="credentials")


class ClientSession(Base):
    __tablename__ = "CLIENT_SESSIONS"

    id         = Column("ID",         RAW(16),     primary_key=True, server_default=text("SYS_GUID()"))
    client_id  = Column("CLIENT_ID",  RAW(16),     ForeignKey("CLIENTS.ID"), nullable=False)
    token_hash = Column("TOKEN_HASH", String(255), nullable=False)
    expires_at = Column("EXPIRES_AT", DateTime,    nullable=False)
    created_at = Column("CREATED_AT", DateTime,    server_default=text("CURRENT_TIMESTAMP"))
    user_agent = Column("USER_AGENT", String(500))
    ip_address = Column("IP_ADDRESS", String(45))

    client = relationship("Client", back_populates="sessions")


class Vm(Base):
    __tablename__ = "VMS"

    id                = Column("ID",                RAW(16),     primary_key=True, server_default=text("SYS_GUID()"))
    client_id         = Column("CLIENT_ID",         RAW(16),     ForeignKey("CLIENTS.ID"), nullable=False)
    ip                = Column("IP",                String(45),  nullable=False)
    hostname          = Column("HOSTNAME",          String(255))
    cloud             = Column("CLOUD",             String(20))  # aws|ibm|oracle|unknown
    has_node_exporter = Column("HAS_NODE_EXPORTER", SmallInteger, server_default=text("0"))
    last_seen_at      = Column("LAST_SEEN_AT",      DateTime)
    discovered_at     = Column("DISCOVERED_AT",     DateTime,    server_default=text("CURRENT_TIMESTAMP"))

    client = relationship("Client", back_populates="vms")


class Cert(Base):
    __tablename__ = "CERTS"

    id             = Column("ID",             RAW(16),     primary_key=True, server_default=text("SYS_GUID()"))
    client_id      = Column("CLIENT_ID",      RAW(16),     ForeignKey("CLIENTS.ID"), nullable=False)
    cert_serial    = Column("CERT_SERIAL",    String(100), nullable=False)
    cert_pem       = Column("CERT_PEM",       Text,        nullable=False)
    fingerprint    = Column("FINGERPRINT",    String(100), nullable=False)
    issued_at      = Column("ISSUED_AT",      DateTime,    server_default=text("CURRENT_TIMESTAMP"))
    expires_at     = Column("EXPIRES_AT",     DateTime,    nullable=False)
    revoked        = Column("REVOKED",        SmallInteger, server_default=text("0"))
    revoked_at     = Column("REVOKED_AT",     DateTime)
    revoked_by     = Column("REVOKED_BY",     String(100))   # admin|system|client
    revoked_reason = Column("REVOKED_REASON", String(100))   # leaked|cancelled|reissued|expired
    last_used_at   = Column("LAST_USED_AT",   DateTime)
    use_count      = Column("USE_COUNT",      Integer,     server_default=text("0"))

    client = relationship("Client", back_populates="certs")

    __table_args__ = (
        Index("IDX_CERTS_FINGERPRINT", "FINGERPRINT"),
    )


class GrafanaAccess(Base):
    __tablename__ = "GRAFANA_ACCESS"

    id             = Column("ID",             RAW(16),     primary_key=True, server_default=text("SYS_GUID()"))
    client_id      = Column("CLIENT_ID",      RAW(16),     ForeignKey("CLIENTS.ID"), unique=True, nullable=False)
    org_id         = Column("ORG_ID",         Integer,     nullable=False)
    grafana_user   = Column("GRAFANA_USER",   String(100), nullable=False)
    grafana_pass   = Column("GRAFANA_PASS",   String(500), nullable=False)  # AES-256 encrypted
    dashboard_uid         = Column("DASHBOARD_UID",         String(100))   # VPC VMs dashboard
    dashboard_url         = Column("DASHBOARD_URL",         String(500))
    laptop_dashboard_uid  = Column("LAPTOP_DASHBOARD_UID",  String(100))   # My Laptop dashboard
    laptop_dashboard_url  = Column("LAPTOP_DASHBOARD_URL",  String(500))
    provisioned_at        = Column("PROVISIONED_AT",        DateTime, server_default=text("CURRENT_TIMESTAMP"))

    client = relationship("Client", back_populates="grafana")
