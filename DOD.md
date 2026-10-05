# Definition of Done — evaluation-framework

> Referência apenas: define quando uma mudança/feature/release está PRONTA.
> Gate canônico: `make test` (backend) e `make frontend-build` (§ npm).

## 1. Escopo
Framework de avaliação de LLM: upload de datasets, runs (judge determinístico
e/ou LLM via myown-llm-gateway) e comparação de resultados.

## 2. DoD por mudança (todo PR)
- [ ] `make test` verde: `ruff check .` + `mypy app` + `pytest` (com as env
      vars inline que o `Settings` exige).
- [ ] Mudança no frontend: `npm run build` (`tsc && vite build`) verde.
- [ ] Comportamento novo/alterado tem teste, incluindo **caminho de erro**
      (ex.: judge LLM fora → `score_overall=None` + motivo, NUNCA `0.0`;
      falha numa sample não derruba a run).
- [ ] Nenhuma falha de dependência vira `500` cru; healthcheck continua ok.
- [ ] Nova variável de ambiente entra no `.env.example` (backend e/ou frontend,
      sem duplicata) — par `API_KEY`/`VITE_API_KEY` quando relevante.
- [ ] Mudança de schema → migração Alembic (aplicada pelo `entrypoint.sh`).
- [ ] Commit convencional + PR revisado.

## 3. DoD por feature (incremento)
- [ ] Endpoint com `response_model`; paginação (`limit`/`offset`) quando lista.
- [ ] Auth (`X-API-Key`) e rate limit aplicados /v1-wide (via `include_router`).
- [ ] README (endpoints/schema/checklist) atualizado.

## 4. DoD de release (produção)
🔴 **Blocking**
- [x] `alembic upgrade head` no entrypoint do container (`entrypoint.sh`).
- [x] `API_KEY` obrigatória em produção (fail-closed no `Settings`).
- [x] `/health` verifica o banco e devolve 503 se não responder.
- [x] Testes reais de API/judges (inclusive falha do judge) e runner E2E.

🟡 **Importante**
- [x] CORS restrito; auth por API key (compare em tempo constante) + rate limit IP.
- [x] Isolamento de falha por sample; commit por sample; recovery de runs órfãs.
- [x] Paginação + índices + `UNIQUE(run_id, sample_id)`; body-size limit.
- [ ] Fila/worker de verdade (hoje `BackgroundTasks` in-process: a run não
      sobrevive a um `docker restart`).
- [ ] Rate limit compartilhado (Redis) — hoje é em memória por processo.

🟢 **Nice-to-have**
- [ ] Métricas Prometheus + tracing (OTel) + alertas.
- [ ] Build estático do frontend (nginx) em vez do vite dev server.
- [ ] Lockfile Python reprodutível (uv/pip-tools).
- [ ] Testes de frontend + eslint; autenticação de usuário de verdade.
