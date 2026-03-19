from urllib.parse import quote_plus
from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Oracle Autonomous Database
    ORACLE_DSN: str = ""
    ORACLE_USER: str = ""
    ORACLE_PASSWORD: str = ""
    ORACLE_WALLET_DIR: str = ""
    ORACLE_WALLET_PASSWORD: str = ""
    DATABASE_URL: str = ""

    @property
    def db_url(self) -> str:
        return f"oracle+oracledb://{self.ORACLE_USER}:{quote_plus(self.ORACLE_PASSWORD)}@{self.ORACLE_DSN}"

    # Grafana
    GRAFANA_URL: str = "http://grafana:3000"
    GRAFANA_ADMIN_USER: str = "admin"
    GRAFANA_ADMIN_PASSWORD: str = "changeme"
    GRAFANA_PUBLIC_URL: str = "https://grafana.everesto.live"

    # Prometheus
    PROMETHEUS_URL: str = "http://prometheus:9090"
    PROMETHEUS_SD_DIR: str = "/app/prometheus_sd"
    PROMETHEUS_RELOAD_URL: str = "http://prometheus:9090/-/reload"

    # Agent / WSS
    AGENT_SERVER_HOST: str = "agent.everesto.live"
    AGENT_SERVER_PORT: int = 8765
    AGENT_IMAGE: str = "ghcr.io/jacer7/maas-vm-agent"
    LAPTOP_AGENT_IMAGE: str = "ghcr.io/jacer7/maas-laptop-agent"

    # Auth
    SECRET_KEY: str = ""
    JWT_EXPIRE_HOURS: int = 24
    ENCRYPTION_KEY: str = ""

    # Email
    SMTP_HOST: str = "smtp.sendgrid.net"
    SMTP_PORT: int = 587
    SMTP_USER: str = "apikey"
    SMTP_PASS: str = ""
    FROM_EMAIL: str = "noreply@everesto.live"

    # SonarQube
    SONAR_HOST_URL: str = "https://sonar.everesto.live"
    SONAR_TOKEN: str = ""

    # App
    FRONTEND_URL: str = "https://maas.everesto.live"
    PLATFORM_PUBLIC_URL: str = "https://api.everesto.live"
    NODE_EXPORTER_DASHBOARD_ID: int = 1860

    @model_validator(mode="after")
    def _check_required(self) -> "Settings":
        missing = [
            name
            for name in ("ORACLE_DSN", "ORACLE_USER", "ORACLE_PASSWORD", "SECRET_KEY", "ENCRYPTION_KEY")
            if not getattr(self, name)
        ]
        if missing:
            raise RuntimeError("Required environment variables are not set. Check your secrets configuration.")
        return self

    class Config:
        env_file = ".env"


settings = Settings()
