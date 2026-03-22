FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY jobfinder/ ./jobfinder/
RUN pip install --no-cache-dir -e ".[semantic]"
# Pre-download the fastembed embedding model (~70MB) to avoid slow first request
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5')"
EXPOSE 8000
CMD ["sh", "-c", "uvicorn jobfinder.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
