FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
COPY app/ app/
COPY alembic.ini .
COPY migrations/ migrations/
RUN pip install --no-cache-dir .
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=5 \
    CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8001/health', timeout=3)" || exit 1
ENTRYPOINT ["./entrypoint.sh"]
