FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

COPY *.py ./
COPY schema.sql ./
COPY collector/ ./collector/
COPY insights/ ./insights/
COPY llm/ ./llm/
COPY validation/ ./validation/
COPY data/ ./data/

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
