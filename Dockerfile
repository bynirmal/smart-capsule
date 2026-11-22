# Smart Capsule — web interface container.
#
# The web app is pure standard-library Python, so there is nothing to compile
# and no build toolchain to install. Only the modules the server imports are
# copied in: the desktop GUI, tests and local data never enter the image.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SMART_CAPSULE_HOME=/data \
    SMART_CAPSULE_HOST=0.0.0.0 \
    SMART_CAPSULE_ALLOW_REMOTE=1 \
    PORT=8765

WORKDIR /app

COPY config.py main.py ./
COPY ai ./ai
COPY core ./core
COPY database ./database
COPY exporters ./exporters
COPY webapp ./webapp

RUN mkdir -p /data \
    && useradd --create-home --uid 10001 app \
    && chown -R app:app /data /app

USER app

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=4s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8765')+'/healthz',timeout=3)"

CMD ["python", "main.py", "--web"]
