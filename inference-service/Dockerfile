# x86 dev / CI build (CUDA 12 + Python 3.11)
FROM nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3.11-venv python3-pip \
        libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Model weights are mounted at runtime via a volume; this creates the cache dir
RUN mkdir -p /models

COPY src/ ./src/

EXPOSE 8001
CMD ["python3", "src/main.py"]
