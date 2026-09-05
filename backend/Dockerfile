# Pinado por digest (não por tag flutuante como "3.11-slim") — Dependabot
# mantém isso atualizado automaticamente (ver .github/dependabot.yml).
FROM python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6
WORKDIR /app
COPY pyproject.toml .
COPY app/ app/
COPY alembic.ini .
COPY migrations/ migrations/
RUN pip install --no-cache-dir .
COPY entrypoint.sh .
# chmod -R a+rX: COPY preserva o modo dos arquivos de origem — se o
# checkout local tiver permissões restritivas (ex: umask 077 => 600), o
# appuser não-root não consegue nem ler alembic.ini/migrations/*. Normaliza
# tudo pra leitura por todos, independente do estado do filesystem de origem.
RUN chmod +x entrypoint.sh \
    && chmod -R a+rX /app \
    && adduser --system --no-create-home --disabled-password --group appuser
USER appuser
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=5 \
    CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8001/health', timeout=3)" || exit 1
ENTRYPOINT ["./entrypoint.sh"]
