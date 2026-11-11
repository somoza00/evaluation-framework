# Atalhos de desenvolvimento espelhando o CI (.github/workflows/ci.yml).
# Uso: make config | make lint | make test | make up ...
.PHONY: config up down build venv lint test frontend-build audit docker-build scan ci migrate-smoke

# Espelha o job `compose-config` do CI. `GATEWAY_API_KEY` é exigida pelo compose
# via `${VAR:?}` (de propósito: sem placeholder silencioso no código), então sem
# um `.env` — como no runner — a interpolação falha antes de validar o arquivo e
# o alvo acusaria a variável, não o YAML. O default abaixo serve só para a
# validação (nada é iniciado); o valor do ambiente/.env continua tendo
# precedência.
config: ## Valida o docker-compose (sem subir nada)
	GATEWAY_API_KEY=$${GATEWAY_API_KEY:-ci-test-key} docker compose config -q

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

# Espelha o job `docker-build` do CI: as DUAS imagens, com as tags de lá
# (`eval-backend:ci` / `eval-frontend:ci`). O `build` acima constrói via
# compose, que monta o Dockerfile num contexto diferente do job do CI — um COPY
# apontando para arquivo renomeado, um `.dockerignore` agressivo demais ou o
# `pip install` do pacote vazio (ordem errada de COPY/RUN) passava por
# ruff/mypy/pytest e só quebrava no CI, com o PR já aberto.
docker-build: ## Builda as duas imagens com as tags do CI (job docker-build)
	docker build -t eval-backend:ci ./backend
	docker build -t eval-frontend:ci ./frontend

# O job `docker-build` do CI também passa cada imagem pelo Trivy
# (severidade CRITICAL,HIGH; `exit-code: 0` = informativo, não gate). Não havia
# alvo local para isso: um CVE crítico na imagem base aparecia só no log do
# GitHub. O Trivy é ferramenta externa (não é dev-dependency), então o alvo
# falha com a instrução de instalação em vez de fingir que varreu.
scan: docker-build ## Varre as duas imagens com Trivy (CRITICAL,HIGH), como no CI
	@command -v trivy >/dev/null 2>&1 || { \
		echo "trivy nao encontrado: instale (ex.: 'pacman -S trivy', 'brew install trivy')"; \
		echo "ou rode: docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy image --severity CRITICAL,HIGH eval-backend:ci"; \
		exit 1; }
	trivy image --severity CRITICAL,HIGH --exit-code 0 eval-backend:ci
	trivy image --severity CRITICAL,HIGH --exit-code 0 eval-frontend:ci

# Roda os jobs do CI que dão para rodar na máquina de dev, na ordem do
# workflow: `compose-config` (valida o docker-compose), backend (ruff + mypy +
# pytest), frontend (npm ci + build), auditoria de CVE das deps e o build das
# imagens. Ficam de fora, de propósito: `migrate-smoke` (precisa do Postgres do
# compose no ar — `docker compose up -d db` antes) e `scan` (precisa do Trivy).
# Quem tem os dois roda `make ci && make migrate-smoke && make scan`.
ci: config test frontend-build audit docker-build ## Sequência do CI local (sem migrate-smoke/scan)

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