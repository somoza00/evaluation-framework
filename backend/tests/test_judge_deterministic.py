"""Testes unitários do DeterministicJudge (lógica pura, sem banco/mocks)."""

import pytest

from app.services.judge_deterministic import DeterministicJudge


def test_fidelity_exact_match() -> None:
    """expected == actual -> score ~1.0."""
    judge = DeterministicJudge()
    score = judge.score_fidelity("o gato subiu na arvore", "o gato subiu na arvore")
    assert score == pytest.approx(1.0)


def test_fidelity_no_overlap() -> None:
    """Sem palavras em comum -> score 0.0."""
    judge = DeterministicJudge()
    assert judge.score_fidelity("abc def ghi", "jkl mno pqr") == 0.0


def test_coherence_short_text() -> None:
    """Texto com menos de 10 palavras -> penalidade (score < 1.0)."""
    judge = DeterministicJudge()
    assert judge.score_coherence("oi") < 1.0


def test_coherence_repetitive() -> None:
    """Mesma palavra em mais de 30% do texto -> penalidade forte."""
    judge = DeterministicJudge()
    score = judge.score_coherence("sim sim sim sim sim sim sim sim sim sim sim sim")
    assert score <= 0.7


def test_instruction_following() -> None:
    """Palavras-chave do prompt presentes na resposta -> score alto."""
    judge = DeterministicJudge()
    score = judge.score_instruction(
        "Explique a arquitetura de microservicos com exemplos de deployment",
        "A arquitetura de microservicos permite deployment independente.",
    )
    assert score >= 0.5


def test_evaluate_returns_all_scores() -> None:
    """evaluate() retorna dict com as 3 chaves de score."""
    judge = DeterministicJudge()
    scores = judge.evaluate("prompt qualquer", "esperado", "resposta do modelo")
    assert set(scores) == {"score_fidelity", "score_coherence", "score_instruction"}
    assert all(0.0 <= value <= 1.0 for value in scores.values())
