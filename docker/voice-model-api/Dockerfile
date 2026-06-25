FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models/huggingface \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /app/requirements.txt

RUN pip uninstall -y torchvision

RUN pip install reportlab==4.4.6

RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY app.py logging_config.py /app/

EXPOSE 8100

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8100"]
