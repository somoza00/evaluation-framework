# Atalhos de desenvolvimento espelhando o CI (.github/workflows/ci.yml).
# Uso: make config | make lint | make test | make up ...
.PHONY: config up down build venv lint test frontend-build audit migrate-smoke

config: ## Valida o docker-compose (sem subir nada)
	docker compose config -q

up: ## Sobe o stack em background
	docker compose up -d --build

down: ## Derruba o stack
	docker compose down

build: ## Builda as imagens
	docker compose build

venv: ## Cria o .venv do backend e instala dev deps
	cd backend && (test -d .venv || python3 -m venv .venv) && .venv/bin/pip install -e ".[dev]"

lint: ## Lint do backend (ruff + mypy)
	cd backend && .venv/bin/ruff check . && .venv/bin/mypy app

test: ## Gate do backend (ruff + mypy + pytest; env minimo p/ o Settings importar)
	cd backend && .venv/bin/ruff check . && .venv/bin/mypy app && DATABASE_URL=sqlite+aiosqlite:// GATEWAY_URL=http://localhost:8000 GATEWAY_API_KEY=ci-test JUDGE_MODEL=deepseek/deepseek-chat .venv/bin/pytest

frontend-build: ## Builda o frontend (npm ci + build, como no CI)
	cd frontend && npm ci && npm run build

# Espelha o job `dependency-audit` do CI: pip-audit quebra o build quando há
# CVE conhecida nas deps Python resolvidas. Não é dev-dependency (o CI instala
# na hora), por isso o alvo faz o mesmo antes de varrer — sem isso, o CVE só
# aparecia depois do push. --skip-editable: o próprio pacote local não existe
# no PyPI para ser auditado.
audit: ## Varredura de CVE nas deps do backend (espelha o job dependency-audit do CI)
	cd backend && .venv/bin/pip install "pip-audit>=2.7.0" "setuptools>=83.0.0" \
		&& .venv/bin/pip-audit --skip-editable

# Espelha o job `migrations` do CI: aplica e desfaz TODAS as migrations contra um
# Postgres de verdade. As migrations usam JSONB, então SQLite (o que o `make
# test` usa) não serve. Roda numa database descartável no Postgres do compose,
# então a base de dev (`evaluation`) não é tocada — exige `docker compose up -d
# db` antes. Sem isto, um erro de revision/DDL só aparecia no startup do
# container, com o serviço fora do ar no deploy.
EVAL_DB_PORT ?= 5434
MIGRATE_SMOKE_DB ?= eval_migsmoke
MIGRATE_SMOKE_URL ?= postgresql+asyncpg://eval:eval@localhost:$(EVAL_DB_PORT)/$(MIGRATE_SMOKE_DB)
MIGRATE_SMOKE_ENV = DATABASE_URL="$(MIGRATE_SMOKE_URL)" GATEWAY_URL=http://localhost:8000 GATEWAY_API_KEY=ci-test JUDGE_MODEL=deepseek/deepseek-chat

migrate-smoke: ## Aplica e desfaz as migrations num Postgres descartável (espelha o job migrations do CI)
	docker compose exec -T db psql -U eval -d evaluation -c "DROP DATABASE IF EXISTS $(MIGRATE_SMOKE_DB);"
	docker compose exec -T db psql -U eval -d evaluation -c "CREATE DATABASE $(MIGRATE_SMOKE_DB);"
	cd backend && $(MIGRATE_SMOKE_ENV) .venv/bin/alembic upgrade head
	cd backend && $(MIGRATE_SMOKE_ENV) .venv/bin/alembic downgrade base