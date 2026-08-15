# evaluation-framework

Framework para avaliar modelos LLM: upload de datasets, execução de avaliações
(judge determinístico e/ou LLM via myown-llm-gateway) e comparação de resultados.

> **Status:** funcional (datasets, runs, judges e comparação implementados e
> testados) — ainda não é production-ready, ver checklist abaixo.

## Stack

- **Backend**: Python 3.11, FastAPI, SQLAlchemy 2.0 (async), Alembic, PostgreSQL 16
- **Frontend**: React 18, TypeScript, Vite, Recharts (fetch nativo, sem axios)
- **Judge LLM**: myown-llm-gateway (OpenAI-compatible) na porta 8000

## Estrutura

```
evaluation-framework/
├── backend/            # FastAPI + SQLAlchemy async + Alembic
│   ├── app/
│   │   ├── api/v1/     # routers: datasets, evaluations, results
│   │   ├── core/       # config (pydantic-settings) + database
│   │   ├── models/     # Dataset, Sample, EvaluationRun, EvaluationResult, enums
│   │   ├── services/   # judge_deterministic, judge_llm, runner
│   │   └── main.py     # entrypoint FastAPI
│   ├── migrations/     # Alembic (env.py async)
│   └── tests/
├── frontend/           # React 18 + Vite + TS
│   └── src/
│       ├── components/ # DatasetUpload, RunEvaluation, ResultsTable, ModelComparison
│       └── pages/      # Datasets, Evaluations, Results
├── docker-compose.yml  # db (5433), backend (8001), frontend (5174)
└── .github/workflows/  # CI: ruff + mypy + pytest / tsc + vite build
```

## Como rodar

```bash
docker compose up --build
```

- Frontend: http://localhost:5174
- Backend API: http://localhost:8001 (docs em /docs)
- Postgres: `localhost:5433` no host (`db:5432` na rede interna)

Para o backend rodando local (fora do compose), crie `backend/.env` a partir de
`backend/.env.example` — **nunca commitar `.env`**.

## Variáveis de ambiente (backend)

| Variável | Descrição | Default (dev) |
|---|---|---|
| `DATABASE_URL` | connection string asyncpg | `postgresql+asyncpg://eval:eval@localhost:5432/evaluation` |
| `GATEWAY_URL` | URL do myown-llm-gateway | `http://localhost:8000` |
| `GATEWAY_API_KEY` | chave virtual do gateway | `sk-local` |
| `JUDGE_MODEL` | modelo usado como judge | `deepseek/deepseek-chat` |
| `API_KEY` | chave da própria API (header `X-API-Key`); vazio = auth desabilitada | _(vazio, dev)_ |
| `RATE_LIMIT_PER_MINUTE` | requests/min por IP antes de 429 | `120` |
| `RUN_CONCURRENCY` | samples processadas em paralelo por run | `5` |
| `TRUST_PROXY_HEADERS` | usa `X-Forwarded-For` (em vez do IP da conexão TCP) no rate limit — só ative atrás de um proxy confiável | `false` |
| `MAX_REQUEST_BODY_BYTES` | corpo de request além disso leva 413 antes de ser lido | `25000000` |

Se `API_KEY` estiver definida, defina também `VITE_API_KEY` (mesmo valor) para
o frontend anexar o header `X-API-Key` nas chamadas — ver `.env.example` na
raiz e `frontend/src/api.ts`.

Com `APP_ENV=production`, o processo **recusa subir sem `API_KEY`** (fail-closed
— ver `Settings` em `app/core/config.py`); `/docs`, `/redoc` e `/openapi.json`
também ficam desabilitados nesse modo.

### Threat model do `X-API-Key` (leia antes de confiar demais nisso)

`API_KEY`/`VITE_API_KEY` é um token de capacidade compartilhado, embutido no
bundle JS do frontend — qualquer um que abra o DevTools no navegador de quem
acessa o frontend consegue ler a chave. Isso é aceitável para uma ferramenta
interna atrás de rede confiável (VPN, rede interna), mas **não** é autenticação
de usuário: não há como revogar o acesso de uma pessoa específica, nem
distinguir quem fez uma run. Para expor isto publicamente ou multi-tenant,
é necessário login de verdade (sessão/cookie) antes de continuar usando
`X-API-Key` só para service-to-service.

## Endpoints (v1)

```
POST /v1/datasets
POST /v1/datasets/{id}/samples
GET  /v1/datasets
POST /v1/evaluations
GET  /v1/evaluations
GET  /v1/evaluations/{id}
GET  /v1/results/{run_id}
GET  /v1/results/compare?runs=id1,id2
```

## Schema (resumo)

- `datasets`: id, name, description, created_at
- `samples`: id, dataset_id, input, expected_output, metadata (jsonb)
- `evaluation_runs`: id, dataset_id, model, judge_type (enum), status (enum), created_at, finished_at
- `evaluation_results`: id, run_id, sample_id, actual_output, scores, judge_reasoning, metadata (jsonb)

## Checklist de produção

🔴 **Blocking**
- [ ] Rodar `alembic upgrade head` no entrypoint do container em produção
      (com `APP_ENV=production` o `create_all` de dev fica desligado — ver `main.py`)
- [x] Migration de índices/unique constraint criada (`migrations/versions/20260815_*`)
- [x] `API_KEY` obrigatória em produção — o processo recusa subir sem ela
      (`APP_ENV=production` + `Settings`, fail-closed)
- [x] `GATEWAY_API_KEY` sem fallback silencioso no compose (`${VAR:?...}`)
- [x] Testes reais de API, judges (incl. falha do LLM judge) e runner E2E

🟡 **Importante**
- [x] CORS restrito à origem do frontend (métodos/headers também restritos)
- [x] Auth por API key (`X-API-Key`, comparação em tempo constante) + rate
      limit por IP (com suporte opcional a `X-Forwarded-For` atrás de proxy)
- [x] Judge LLM: falha vira `score=None` + motivo, nunca `0.0`
- [x] Retry com backoff (429/5xx) nas chamadas ao gateway
- [x] Processamento de samples concorrente (`RUN_CONCURRENCY`) + isolamento
      de falha por sample (uma sample com erro não derruba a run inteira)
- [x] Commit por sample (não mais um único commit no fim da run)
- [x] Recovery de runs presas em `RUNNING` num restart (sweep no startup)
- [x] `/health` verifica o banco (sem vazar detalhe de exceção em produção);
      healthcheck do backend no compose
- [x] Paginação em `GET /datasets` e `GET /evaluations`
- [x] Índices nas FKs + `UNIQUE(run_id, sample_id)`
- [x] Logs estruturados (JSON) + request-id por request; eventos de auth
      (401/429) num logger dedicado (`app.security`)
- [x] Validação de tamanho de payload (por campo, por request via
      `MaxBodySizeMiddleware`, e por nº de samples)
- [x] `/docs`, `/redoc`, `/openapi.json` desabilitados em produção
- [x] Imagens Docker pinadas por digest + container roda non-root + CI
      builda e escaneia (Trivy) as imagens
- [x] `pip-audit` no CI + Dependabot (pip/npm/docker/actions)
- [ ] Fila/worker de verdade (ex: arq) — hoje ainda é `BackgroundTasks`
      in-process; a run não sobrevive a um `docker restart` (mas os
      resultados já persistidos, sim — commit é por sample)
- [ ] Rate limit compartilhado (Redis) — o atual é em memória por processo:
      reinicia com o processo e não é compartilhado entre workers/réplicas.
      Só vale a pena quando o deploy real tiver mais de 1 worker.

🟢 **Nice-to-have**
- [ ] Métricas Prometheus + tracing (OTel) + alertas
- [ ] Build estático do frontend (nginx) em vez do vite dev server no container
- [ ] `ON DELETE CASCADE` + estratégia de backup do Postgres
- [ ] Testes de frontend + eslint
- [ ] CD (build/push de imagem no main)
- [ ] Lockfile de dependências Python (pip-tools/uv) — hoje `pyproject.toml`
      usa ranges (`>=`); build não é 100% reprodutível
- [ ] Autenticação de usuário de verdade (sessão/cookie) em vez de uma
      API key compartilhada — ver "Threat model" acima
