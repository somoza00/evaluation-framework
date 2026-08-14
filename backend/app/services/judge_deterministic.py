"""Judge determinístico: pontuação por regras locais (sem chamada a LLM)."""

from typing import Any


class DeterministicJudge:
    """Compara actual_output com expected_output usando heurísticas.

    Responsável pelos scores de fidelity (e derivados) quando
    judge_type é ``deterministic`` ou ``both``.
    """

    def score(self, actual_output: str, expected_output: str) -> dict[str, Any]:
        """Retorna {score_fidelity, score_coherence, score_instruction, score_overall}."""
        raise NotImplementedError

    def _normalize(self, text: str) -> str:
        """Normaliza o texto (case/whitespace) antes de comparar."""
        raise NotImplementedError
