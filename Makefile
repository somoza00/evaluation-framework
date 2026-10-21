# Atalhos de desenvolvimento espelhando o CI (.github/workflows/ci.yml).
# Uso: make config | make lint | make test | make up ...
.PHONY: config up down build venv lint test frontend-build audit

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