FROM python:3.12-slim

WORKDIR /app

# Install system deps for python-oracledb thick mode
RUN apt-get update && apt-get install -y --no-install-recommends \
    libaio1 libssl-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x start.sh

EXPOSE 8000 8765

CMD ["./start.sh"]
