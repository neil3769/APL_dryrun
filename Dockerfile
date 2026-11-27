FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=5000 \
    DATABASE_PATH=/data/enrollment.db

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py db.py schemas.py openapi.py ./

RUN mkdir -p /data

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/api/health', timeout=2)" || exit 1

CMD ["python", "-u", "app.py"]
