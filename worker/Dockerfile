FROM python:3.12-slim
WORKDIR /code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY worker.py .
# Print logs immediately instead of buffering them, so `docker compose logs` is live.
ENV PYTHONUNBUFFERED=1
CMD ["python", "worker.py"]
