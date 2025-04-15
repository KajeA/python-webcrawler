FROM python:3.12-slim

WORKDIR /app

# PostgreSQL
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY crawler.py scheduler.py ./

COPY api.py .

EXPOSE 8000

CMD ["python", "api.py"]
