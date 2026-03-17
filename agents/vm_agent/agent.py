"""
Everesto monitoring agent.
Connects OUTBOUND to platform WSS server using mTLS client certificate.
Reconnects automatically on network errors. Stops on close code 4403 (revoked/disabled).
"""
import asyncio
import base64
import os
import ssl
import tempfile
import websockets

PLATFORM_URL = os.environ["PLATFORM_URL"]
CLIENT_CERT  = base64.b64decode(os.environ["CLIENT_CERT"])
CLIENT_KEY   = base64.b64decode(os.environ["CLIENT_KEY"])
CA_CERT      = base64.b64decode(os.environ["CA_CERT"])

RECONNECT_INITIAL = 5    # seconds
RECONNECT_MAX     = 120  # seconds


def build_ssl_context() -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.verify_mode = ssl.CERT_REQUIRED

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as ca_f:
        ca_f.write(CA_CERT)
        ca_path = ca_f.name

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as cert_f:
        cert_f.write(CLIENT_CERT)
        cert_path = cert_f.name

    with tempfile.NamedTemporaryFile(delete=False, suffix=".key") as key_f:
        key_f.write(CLIENT_KEY)
        key_path = key_f.name

    ctx.load_verify_locations(ca_path)
    ctx.load_cert_chain(cert_path, key_path)
    return ctx


async def connect():
    ctx   = build_ssl_context()
    delay = RECONNECT_INITIAL

    while True:
        try:
            print(f"Connecting to {PLATFORM_URL}…")
            async with websockets.connect(PLATFORM_URL, ssl=ctx) as ws:
                print("Connected.")
                delay = RECONNECT_INITIAL  # reset backoff on success
                async for _ in ws:
                    pass  # keep alive, platform drives the conversation

        except websockets.exceptions.ConnectionClosedError as e:
            if e.code == 4403:
                print(f"Connection rejected: {e.reason}. Agent stopping.")
                return  # do NOT reconnect on revoke/disable

            print(f"Connection closed ({e.code}). Reconnecting in {delay}s…")

        except (OSError, websockets.exceptions.WebSocketException) as e:
            print(f"Connection error: {e}. Reconnecting in {delay}s…")

        await asyncio.sleep(delay)
        delay = min(delay * 2, RECONNECT_MAX)


if __name__ == "__main__":
    asyncio.run(connect())
