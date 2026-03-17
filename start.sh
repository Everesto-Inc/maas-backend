#!/bin/bash
set -e

# Bootstrap CA and server cert if needed (both processes need it)
python -c "
from core.cert_authority import bootstrap_ca, bootstrap_server_cert, CA_CERT_PATH, SERVER_CERT_PATH
if not CA_CERT_PATH.exists():
    bootstrap_ca()
if not SERVER_CERT_PATH.exists():
    bootstrap_server_cert()
print('Certs ready.')
"

# Start the WSS agent server in background
python core/agent_server_standalone.py &
AGENT_PID=$!

# Start the FastAPI server (foreground)
exec uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
