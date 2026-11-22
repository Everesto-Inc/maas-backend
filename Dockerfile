FROM python:3.15-slim

# Non-root user (fixed uid → predictable file ownership on volumes)
RUN useradd --create-home --uid 10001 --user-group app

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The app writes at runtime into /app (certs/, prometheus_sd/) → owned by the app user
COPY --chown=app:app . .

RUN chmod +x start.sh

EXPOSE 8000 8765

USER app

CMD ["./start.sh"]
