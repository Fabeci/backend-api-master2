# ---- Backend Django / DRF — SOMAPRO ----
# Image de développement local ; production = cPanel (utilisateur dédié, sans Docker).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dépendances système (build éventuel + Pillow/magic)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libjpeg62-turbo-dev \
        zlib1g-dev \
        tesseract-ocr \
        tesseract-ocr-fra \
        poppler-utils \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Requirements nettoyés (UTF-8) — le requirements.txt d'origine est en UTF-16
# et contient un pin inexistant (click-plugins==1.1.1.2).
COPY requirements.docker.txt /app/requirements.docker.txt
RUN pip install --no-cache-dir --timeout 120 --retries 5 -r /app/requirements.docker.txt

# Code applicatif (db.sqlite3 et media sont montés par docker-compose)
# .dockerignore exclut secrets/données ; image de dev non déployée.
COPY . /app/

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
