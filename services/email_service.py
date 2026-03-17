import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import settings


async def _send(to: str, subject: str, html: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.FROM_EMAIL
    msg["To"] = to
    msg.attach(MIMEText(html, "html"))

    await aiosmtplib.send(
        msg,
        hostname=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        username=settings.SMTP_USER,
        password=settings.SMTP_PASS,
        start_tls=True,
    )


async def send_welcome_email(to: str, full_name: str, slug: str):
    html = f"""
    <h2>Welcome to Everesto, {full_name}!</h2>
    <p>Your account has been created. Your client ID is: <strong>{slug}</strong></p>
    <p>Next step: complete your onboarding to connect your infrastructure.</p>
    <p><a href="{settings.FRONTEND_URL}/onboard">Start onboarding →</a></p>
    """
    await _send(to, "Welcome to Everesto — complete your setup", html)


async def send_password_reset_email(to: str, reset_token: str):
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
    html = f"""
    <h2>Password Reset</h2>
    <p>Click the link below to reset your password. It expires in 1 hour.</p>
    <p><a href="{reset_url}">Reset password →</a></p>
    <p>If you didn't request this, ignore this email.</p>
    """
    await _send(to, "Everesto — reset your password", html)


async def send_new_docker_command_email(to: str, full_name: str, docker_command: str):
    html = f"""
    <h2>Your new agent command, {full_name}</h2>
    <p>Your previous certificate has been renewed. Run this command on your VM to reconnect your agent:</p>
    <pre style="background:#f4f4f4;padding:12px;border-radius:6px">{docker_command}</pre>
    <p>Your old agent will be disconnected automatically.</p>
    """
    await _send(to, "Everesto — new agent command required", html)


async def send_cert_expiry_warning(to: str, full_name: str, days_left: int, docker_command: str):
    html = f"""
    <h2>Your monitoring certificate expires in {days_left} days</h2>
    <p>Hi {full_name}, your agent certificate will expire soon. Run this updated command to renew it:</p>
    <pre style="background:#f4f4f4;padding:12px;border-radius:6px">{docker_command}</pre>
    """
    await _send(to, f"Everesto — agent certificate expires in {days_left} days", html)
