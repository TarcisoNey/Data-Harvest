FROM python:3.12-slim

WORKDIR /app

# Só o necessário para o ETL: a imagem não precisa de chromadb, streamlit etc.
COPY requirements-etl.txt .
RUN pip install --no-cache-dir -r requirements-etl.txt

COPY src/etl.py src/database.py src/

CMD ["python", "src/etl.py"]
