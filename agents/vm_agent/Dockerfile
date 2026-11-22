FROM python:3.12-slim

# Non-root user — the agent only writes temp files (tempfile → /tmp)
RUN useradd --create-home --uid 10001 --user-group agent

WORKDIR /app
RUN pip install websockets

COPY agent.py .

USER agent

CMD ["python", "agent.py"]
