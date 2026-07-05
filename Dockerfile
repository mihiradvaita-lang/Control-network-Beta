FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
COPY config/ ./config/
COPY skills/ ./skills/
EXPOSE 8000
# tmpfs /tmp recommended at runtime for ZDR: docker run --tmpfs /tmp ...
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
