FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive
ENV PIP_NO_CACHE_DIR=1
ENV PYTHONUNBUFFERED=1
ENV QT_QPA_PLATFORM=xcb

ARG INSTALL_OPTIONAL=false

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    fonts-noto-cjk \
    fonts-noto-color-emoji \
    git \
    libdbus-1-3 \
    libegl1 \
    libfontconfig1 \
    libfreetype6 \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libsndfile1 \
    libxext6 \
    libxkbcommon-x11-0 \
    libxcb-cursor0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render-util0 \
    libxcb-shape0 \
    libxcb-xfixes0 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-core.txt requirements-yolo.txt requirements-optional.txt ./

RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements-core.txt \
    && python -m pip install -r requirements-yolo.txt \
    && if [ "$INSTALL_OPTIONAL" = "true" ]; then python -m pip install -r requirements-optional.txt; fi

COPY . .

CMD ["python", "main.py"]
