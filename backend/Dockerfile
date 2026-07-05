FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir maigret && \
    pip install --no-cache-dir -r requirements.txt

COPY *.py ./
COPY schema.sql ./
COPY collector/ ./collector/
COPY insights/ ./insights/
COPY llm/ ./llm/
COPY reporting/ ./reporting/
COPY validation/ ./validation/
COPY data/ ./data/

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
