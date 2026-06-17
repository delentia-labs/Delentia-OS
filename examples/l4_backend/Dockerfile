# Dockerfile for Delentia OS L4 Model Backend
FROM pytorch/pytorch:2.2.1-cuda12.1-cudnn8-runtime

WORKDIR /app

# Install system dependencies for build tools and curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies for transformers and FastAPI
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    pydantic \
    transformers \
    accelerate \
    peft \
    bitsandbytes \
    safetensors \
    huggingface_hub

COPY backend_main.py .

# Expose port (7860 is Hugging Face Spaces default port)
EXPOSE 7860

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV RCT_BASE_MODEL="unsloth/llama-3-8b-Instruct-bnb-4bit"
ENV RCT_ADAPTER_MODEL="Delentia/delentia-guardian-adapter-v1.3"

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:7860/health || exit 1

CMD ["uvicorn", "backend_main:app", "--host", "0.0.0.0", "--port", "7860"]
