FROM python:3.12-slim

WORKDIR /app
RUN pip install websockets

COPY agent.py .

CMD ["python", "agent.py"]
