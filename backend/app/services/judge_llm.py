"""Judge via LLM: pontua samples chamando o myown-llm-gateway.

O gateway é OpenAI-compatible e fica em GATEWAY_URL (ex: http://localhost:8000);
o modelo usado é o de JUDGE_MODEL, autenticado com GATEWAY_API_KEY.
"""

from typing import Any

import httpx


class LLMJudge:
    """Envia o prompt de judge ao gateway e parseia os scores retornados."""

    _client: httpx.AsyncClient

    def __init__(self) -> None:
        """Monta o AsyncClient apontando para GATEWAY_URL com a API key."""
        raise NotImplementedError

    async def score(
        self, sample_input: str, actual_output: str, expected_output: str
    ) -> dict[str, Any]:
        """Retorna {score_fidelity, score_coherence, score_instruction,
        score_overall, judge_reasoning} para um sample."""
        raise NotImplementedError
