"""Testes do LLMJudge: parse de score e o contrato de falha (None, nunca 0.0)."""

import httpx
import pytest

from app.services.judge_llm import LLMJudge


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove o backoff real do retry para os testes rodarem instantâneos."""

    async def _noop(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr("app.services.http_retry.asyncio.sleep", _noop)


def _judge_with_transport(handler: httpx.MockTransport | object) -> LLMJudge:
    judge = LLMJudge(gateway_url="http://test", api_key="k", model="m")
    judge.client = httpx.AsyncClient(transport=handler, base_url="http://test")
    return judge


async def test_evaluate_success_normalizes_score() -> None:
    """score=4 (1-5) deve normalizar para 0.75 ((4-1)/4)."""

    async def handler(request: httpx.Request) -> httpx.Response:
        body = {"choices": [{"message": {"content": '{"score": 4, "reasoning": "boa resposta"}'}}]}
        return httpx.Response(200, json=body)

    judge = _judge_with_transport(httpx.MockTransport(handler))
    try:
        result = await judge.evaluate("prompt", "esperado", "atual")
    finally:
        await judge.close()

    assert result["score_overall"] == 0.75
    assert result["judge_reasoning"] == "boa resposta"


async def test_evaluate_http_failure_returns_none_not_zero() -> None:
    """Falha do gateway deve virar score_overall=None — 0.0 seria uma nota falsa."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    judge = _judge_with_transport(httpx.MockTransport(handler))
    try:
        result = await judge.evaluate("prompt", "esperado", "atual")
    finally:
        await judge.close()

    assert result["score_overall"] is None
    assert "erro ao avaliar via LLM" in str(result["judge_reasoning"])


async def test_evaluate_malformed_response_returns_none() -> None:
    """Resposta sem o campo 'score' também é falha do judge, não nota 0."""

    async def handler(request: httpx.Request) -> httpx.Response:
        body = {"choices": [{"message": {"content": "não sou json"}}]}
        return httpx.Response(200, json=body)

    judge = _judge_with_transport(httpx.MockTransport(handler))
    try:
        result = await judge.evaluate("prompt", "esperado", "atual")
    finally:
        await judge.close()

    assert result["score_overall"] is None


def _judge() -> LLMJudge:
    return LLMJudge(gateway_url="http://test", api_key="k", model="m")


def test_parse_score_accepts_unquoted_text() -> None:
    """Modelo que responde `Score: 4` (sem aspas/JSON) não deve derrubar o judge.

    Antes, o fallback só casava `"score": <int>`: um texto como
    `Score: 4/5 — Reasoning: boa` levantava ValueError e a sample ficava sem
    nota (score_overall=None), zerando a média da run sem motivo real.
    """
    judge = _judge()
    score, reasoning = judge._parse_score("Score: 4/5\nReasoning: atende ao pedido")
    assert score == 4
    assert reasoning == "atende ao pedido"


def test_parse_score_accepts_decimal_and_comma() -> None:
    """Score decimal (4.5) ou com vírgula (4,5) é truncado para int, não rejeitado."""
    judge = _judge()
    assert judge._parse_score('{"score": 4.5, "reasoning": "ok"}')[0] == 4
    assert judge._parse_score("score: 4,5 — reasoning: ok")[0] == 4


def test_parse_score_accepts_numeric_string_in_json() -> None:
    """JSON válido com score em string ("4.0") também é aceito."""
    judge = _judge()
    assert judge._parse_score('{"score": "4.0", "reasoning": "ok"}')[0] == 4


def test_parse_score_clamps_out_of_range() -> None:
    """Score fora de 1-5 é preso na faixa (a normalização assume 1..5)."""
    judge = _judge()
    assert judge._parse_score('{"score": 9, "reasoning": "ok"}')[0] == 5
    assert judge._parse_score('{"score": 0, "reasoning": "ok"}')[0] == 1


async def test_evaluate_unquoted_content_still_scores() -> None:
    """Ponta a ponta: conteúdo solto vira nota normalizada em vez de None."""

    async def handler(request: httpx.Request) -> httpx.Response:
        body = {"choices": [{"message": {"content": "Score: 3 — Reasoning: parcialmente correto"}}]}
        return httpx.Response(200, json=body)

    judge = _judge_with_transport(httpx.MockTransport(handler))
    try:
        result = await judge.evaluate("prompt", "esperado", "atual")
    finally:
        await judge.close()

    assert result["score_overall"] == 0.5
    assert "parcialmente correto" in str(result["judge_reasoning"])
