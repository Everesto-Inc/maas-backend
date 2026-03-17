"""
mTLS certificate authority.

bootstrap_ca()      — run ONCE on server setup to create the CA keypair
issue_client_cert() — called on each new onboarding to issue a client cert
"""
import base64
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from config import settings

CA_CERT_PATH = Path("certs/ca/ca.crt")
CA_KEY_PATH  = Path("certs/ca/ca.key")


SERVER_CERT_PATH = Path("certs/server/server.crt")
SERVER_KEY_PATH  = Path("certs/server/server.key")


def bootstrap_server_cert():
    """Generate server TLS cert signed by CA. Called automatically if cert missing."""
    ca_cert, ca_key = _load_ca()
    SERVER_CERT_PATH.parent.mkdir(parents=True, exist_ok=True)

    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Everesto Agent Server")]))
        .issuer_name(ca_cert.subject)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.ExtendedKeyUsage([x509.ExtendedKeyUsageOID.SERVER_AUTH]), critical=True)
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.DNSName("backend"),
                x509.DNSName("agent-server"),
                x509.IPAddress(__import__("ipaddress").ip_address("127.0.0.1")),
            ]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    SERVER_KEY_PATH.write_bytes(
        server_key.private_bytes(serialization.Encoding.PEM,
                                 serialization.PrivateFormat.TraditionalOpenSSL,
                                 serialization.NoEncryption())
    )
    SERVER_CERT_PATH.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print(f"Server cert created: {SERVER_CERT_PATH}")


def bootstrap_ca():
    """Generate CA keypair. Run once: python -c "from core.cert_authority import bootstrap_ca; bootstrap_ca()" """
    CA_CERT_PATH.parent.mkdir(parents=True, exist_ok=True)

    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    now = datetime.now(timezone.utc)
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Everesto Root CA")]))
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Everesto Root CA")]))
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=3650))  # 10 years
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )

    CA_KEY_PATH.write_bytes(
        ca_key.private_bytes(serialization.Encoding.PEM,
                             serialization.PrivateFormat.TraditionalOpenSSL,
                             serialization.NoEncryption())
    )
    CA_CERT_PATH.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    print(f"CA created: {CA_CERT_PATH} / {CA_KEY_PATH}")


def _load_ca():
    ca_cert = x509.load_pem_x509_certificate(CA_CERT_PATH.read_bytes())
    ca_key  = serialization.load_pem_private_key(CA_KEY_PATH.read_bytes(), password=None)
    return ca_cert, ca_key


def issue_client_cert(client_slug: str) -> dict:
    """
    Issue mTLS client cert for the given slug.
    Returns:
        cert_pem, key_pem, ca_pem   — PEM strings
        fingerprint                  — SHA-256 hex of cert DER
        cert_serial                  — hex serial number
        expires_at                   — datetime
    """
    ca_cert, ca_key = _load_ca()

    client_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=365)

    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, client_slug),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "MaaS Client"),
        ]))
        .issuer_name(ca_cert.subject)
        .public_key(client_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(expires_at)
        .add_extension(x509.ExtendedKeyUsage([x509.ExtendedKeyUsageOID.CLIENT_AUTH]), critical=True)
        .sign(ca_key, hashes.SHA256())
    )

    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    key_pem  = client_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()
    ca_pem       = CA_CERT_PATH.read_text()
    fingerprint  = hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()
    cert_serial  = format(cert.serial_number, "x")

    return {
        "cert_pem":    cert_pem,
        "key_pem":     key_pem,
        "ca_pem":      ca_pem,
        "fingerprint": fingerprint,
        "cert_serial": cert_serial,
        "expires_at":  expires_at,
    }


def build_docker_command(client_slug: str, cert_pem: str, key_pem: str, ca_pem: str) -> str:
    cert_b64 = base64.b64encode(cert_pem.encode()).decode()
    key_b64  = base64.b64encode(key_pem.encode()).decode()
    ca_b64   = base64.b64encode(ca_pem.encode()).decode()

    return (
        f"docker run -d --name monitor-agent --restart always \\\n"
        f"  --network maas_default \\\n"
        f"  -e PLATFORM_URL=wss://{settings.AGENT_SERVER_HOST} \\\n"
        f"  -e CLIENT_CERT={cert_b64} \\\n"
        f"  -e CLIENT_KEY={key_b64} \\\n"
        f"  -e CA_CERT={ca_b64} \\\n"
        f"  {settings.AGENT_IMAGE}:latest"
    )
