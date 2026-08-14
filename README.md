# evaluation-framework

Framework para avaliar modelos LLM: upload de datasets, execução de avaliações
(judge determinístico e/ou LLM via myown-llm-gateway) e comparação de resultados.

> **Status: SCAFFOLDING** — estrutura completa, sem lógica implementada.

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
- [ ] Migrations Alembic aplicadas (nada de `create_all` em produção)
- [ ] `GATEWAY_API_KEY` real fora de código/repo (secret manager)
- [ ] Testes reais de API, judges e runner

🟡 **Importante**
- [ ] CORS restrito à origem do frontend
- [ ] Paginação em `GET /datasets` e `GET /evaluations`
- [ ] Timeout/retry nas chamadas ao gateway (LLMJudge)

🟢 **Nice-to-have**
- [ ] Fila/worker (ex: arq ou celery) para runs longas
- [ ] Logs estruturados (structlog) e métricas das runs
