"""Métricas Prometheus do runner/worker.

O eval não expunha NENHUMA métrica: o desfecho de uma run só aparecia abrindo a
UI (ou consultando o banco). Não dava para alertar em "três runs FAILED em dez
minutos" nem enxergar a proporção de samples que ficaram sem nota (falha do
judge = `score_overall=None`) — que é justamente o sinal de que o gateway/juiz
está fora. Os contadores são incrementados no `runner` e expostos em `/metrics`
no formato de scrape padrão do Prometheus.

Escopo mínimo e honesto: só contadores/histograma incrementados no caminho que
já é exercitado (runner). Nada aqui lê banco nem altera o comportamento dos
endpoints existentes.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

RUNS_FINISHED = Counter(
    "eval_runs_finished_total",
    "Runs finalizadas pelo runner, por status ('done' ou 'failed').",
    ["status"],
)

RESULTS_PERSISTED = Counter(
    "eval_results_persisted_total",
    "Resultados persistidos (um por sample), por desfecho do julgamento.",
    # scored   = o judge devolveu nota (score_overall não nulo)
    # unscored = judge falhou / modelo falhou (score_overall nulo, motivo em judge_reasoning)
    ["outcome"],
)

RUN_DURATION_SECONDS = Histogram(
    "eval_run_duration_seconds",
    "Duração de uma run finalizada pelo runner, em segundos.",
    # Faixas de uma run de LLM: de segundos (dataset pequeno, cache) a dezenas
    # de minutos (centenas de samples com RUN_CONCURRENCY baixo).
    buckets=(1, 5, 15, 30, 60, 120, 300, 600, 1800),
)


def record_run_finished(*, status: str, duration_seconds: float) -> None:
    """Contabiliza o desfecho de uma run (status + duração)."""
    RUNS_FINISHED.labels(status=status).inc()
    RUN_DURATION_SECONDS.observe(max(0.0, duration_seconds))


def record_result(*, outcome: str) -> None:
    """Contabiliza um resultado persistido ('scored' ou 'unscored')."""
    RESULTS_PERSISTED.labels(outcome=outcome).inc()
