#!/bin/sh
# Roda as migrations Alembic antes de subir a API — sem isso, produção
# dependia do create_all no startup do FastAPI (dev-only, sem histórico de
# schema). Idempotente: "upgrade head" é no-op se o banco já está atualizado.
set -e
alembic upgrade head
# --limit-concurrency: teto grosseiro de conexões simultâneas (não existe
# flag de tamanho de body no uvicorn — isso é feito em app/core/body_limit.py).
exec uvicorn app.main:app --host 0.0.0.0 --port 8001 --limit-concurrency 100
