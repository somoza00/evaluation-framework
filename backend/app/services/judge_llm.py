"""Judge via LLM: chama o myown-llm-gateway (OpenAI-compatible) para avaliar.

O gateway fica em GATEWAY_URL (ex: http://localhost:8000); o modelo usado é
o de JUDGE_MODEL, autenticado com GATEWAY_API_KEY (Bearer).
"""

import json
import re
from typing import Any

import httpx

_SCORE_RE = re.compile(r'"score"\s*:\s*(\d+)')
_REASONING_RE = re.compile(r'"reasoning"\s*:\s*"([^"]+)"')


class LLMJudge:
    """Pontua respostas via LLM: pede JSON {"score": 1-5, "reasoning": "..."}."""

    def __init__(self, gateway_url: str, api_key: str, model: str) -> None:
        """Monta o AsyncClient apontando para o gateway (timeout 60s)."""
        self.client = httpx.AsyncClient(base_url=gateway_url, timeout=60.0)
        self.api_key = api_key
        self.model = model

    async def evaluate(
        self,
        input_prompt: str,
        expected_output: str,
        actual_output: str,
    ) -> dict[str, float | str]:
        """Monta system prompt com rubrica e pede score_overall (1-5) + reasoning.

        Normaliza o score de 1-5 para 0.0-1.0 antes de retornar.
        Erros de HTTP/parse são tratados graciosamente: retorna score 0.0
        com a descrição do erro em judge_reasoning.
        """
        system_prompt = (
            "Você é um juiz de avaliação de respostas de modelos de linguagem. "
            "Avalie a resposta do modelo com base na rubrica:\n"
            "- Fidelidade: a resposta atende ao pedido e corresponde ao esperado?\n"
            "- Coerência: a resposta é clara, completa e sem repetições?\n"
            "- Instrução: a resposta segue as instruções do prompt?\n"
            'Responda APENAS com JSON no formato: {"score": <1-5>, "reasoning": "<justificativa em português>"}'
        )
        user_prompt = (
            f"Prompt: {input_prompt}\n\n"
            f"Resposta esperada: {expected_output}\n\n"
            f"Resposta do modelo: {actual_output}"
        )
        try:
            response = await self.client.post(
                "/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.0,
                },
            )
            response.raise_for_status()
            content: Any = response.json()["choices"][0]["message"]["content"]
            score, reasoning = self._parse_score(str(content))
            return {"score_overall": (score - 1) / 4, "judge_reasoning": reasoning}
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            return {"score_overall": 0.0, "judge_reasoning": f"erro ao avaliar via LLM: {exc}"}

    def _parse_score(self, content: str) -> tuple[int, str]:
        """Extrai score (1-5) e reasoning do JSON retornado pelo modelo.

        Tenta json.loads primeiro; em caso de texto com ruído (ex: markdown),
        faz fallback com regex. Levanta ValueError se não conseguir extrair.
        """
        try:
            data = json.loads(content)
            score = int(data["score"])
            reasoning = str(data["reasoning"])
        except (json.JSONDecodeError, KeyError, TypeError):
            score_match = _SCORE_RE.search(content)
            reasoning_match = _REASONING_RE.search(content)
            if score_match is None:
                raise ValueError(f"resposta do judge sem campo 'score': {content[:200]}")
            score = int(score_match.group(1))
            reasoning = reasoning_match.group(1) if reasoning_match else "sem reasoning"
        return max(1, min(5, score)), reasoning

    async def close(self) -> None:
        """Fecha o AsyncClient HTTP."""
        await self.client.aclose()
