"""Runner: orquestra a avaliação de uma EvaluationRun de ponta a ponta."""

import asyncio
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.time import utcnow_naive
from app.models.dataset import Sample
from app.models.evaluation import (
    EvaluationResult,
    EvaluationRun,
    JudgeType,
    RunStatus,
)
from app.services.http_retry import post_with_retry
from app.services.judge_deterministic import DeterministicJudge
from app.services.judge_llm import LLMJudge


class EvaluationRunner:
    """Coordena modelo avaliado + judges e persiste EvaluationResult por sample."""

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        """Recebe a sessão de banco e as settings da aplicação."""
        self.session = session
        self.settings = settings
        self.det_judge = DeterministicJudge()
        self.llm_judge = LLMJudge(
            gateway_url=settings.GATEWAY_URL,
            api_key=settings.GATEWAY_API_KEY,
            model=settings.JUDGE_MODEL,
        )

    async def close(self) -> None:
        """Fecha o client HTTP do LLMJudge (chamar sempre após run(), inclusive em falha)."""
        await self.llm_judge.close()

    async def run(self, run_id: uuid.UUID) -> None:
        """Executa uma run completa: pending -> running -> done (ou failed).

        1. Busca EvaluationRun, seta status=RUNNING e commita
        2. Busca todos os Samples do dataset associado
        3. Processa as samples concorrentemente (RUN_CONCURRENCY de cada vez):
           chama o modelo avaliado via gateway, roda o judge conforme
           run.judge_type e monta um EvaluationResult
        4. Persiste um EvaluationResult por vez, com commit por sample — uma
           run com 500 samples não perde tudo se o processo morrer no meio
        5. Falha ao chamar o modelo em UMA sample vira um EvaluationResult de
           erro (score=None + motivo); não derruba a run inteira
        6. Seta status=DONE + finished_at e commita
        7. Em exceção estrutural (ex: falha ao buscar samples/banco): seta
           status=FAILED, commita e re-levanta
        """
        run = await self.session.get(EvaluationRun, run_id)
        if run is None:
            raise ValueError(f"EvaluationRun {run_id} não encontrada")

        run.status = RunStatus.RUNNING
        await self.session.commit()

        try:
            samples = (
                await self.session.execute(
                    select(Sample).where(Sample.dataset_id == run.dataset_id)
                )
            ).scalars().all()

            semaphore = asyncio.Semaphore(max(1, self.settings.RUN_CONCURRENCY))

            async def process(sample: Sample) -> EvaluationResult:
                async with semaphore:
                    try:
                        actual_output = await self._call_model(run.model, sample.input)
                    except (httpx.HTTPError, KeyError, IndexError) as exc:
                        return EvaluationResult(
                            run_id=run.id,
                            sample_id=sample.id,
                            actual_output="",
                            judge_reasoning=f"erro ao chamar o modelo avaliado: {exc}",
                        )
                    return await self._build_result(run, sample, actual_output)

            # As chamadas de rede (modelo + judge) rodam concorrentemente;
            # a persistência abaixo é sequencial (AsyncSession não é
            # thread/task-safe para escrita concorrente).
            results = await asyncio.gather(*(process(sample) for sample in samples))
            for result in results:
                self.session.add(result)
                await self.session.commit()

            run.status = RunStatus.DONE
            run.finished_at = utcnow_naive()
            await self.session.commit()
        except Exception:
            # Se a exceção veio de um flush/commit (ex: IntegrityError), a
            # transação já foi abortada pelo driver — sem rollback aqui, o
            # commit abaixo levanta PendingRollbackError e mascara o erro
            # original, deixando a run presa em RUNNING.
            await self.session.rollback()
            run.status = RunStatus.FAILED
            await self.session.commit()
            raise

    async def _build_result(
        self,
        run: EvaluationRun,
        sample: Sample,
        actual_output: str,
    ) -> EvaluationResult:
        """Monta o EvaluationResult conforme o JudgeType da run."""
        if run.judge_type == JudgeType.DETERMINISTIC:
            det = self.det_judge.evaluate(sample.input, sample.expected_output, actual_output)
            return EvaluationResult(
                run_id=run.id,
                sample_id=sample.id,
                actual_output=actual_output,
                score_fidelity=det["score_fidelity"],
                score_coherence=det["score_coherence"],
                score_instruction=det["score_instruction"],
                score_overall=sum(det.values()) / len(det),
            )

        llm = await self.llm_judge.evaluate(
            sample.input, sample.expected_output, actual_output
        )
        llm_score = llm["score_overall"]
        llm_score_val = float(llm_score) if llm_score is not None else None
        reasoning = str(llm["judge_reasoning"])

        if run.judge_type == JudgeType.LLM:
            return EvaluationResult(
                run_id=run.id,
                sample_id=sample.id,
                actual_output=actual_output,
                score_overall=llm_score_val,
                judge_reasoning=reasoning,
            )

        # BOTH: combina scores parciais do determinístico com o overall do
        # LLM. Se o judge LLM falhou (llm_score_val None), score_overall
        # também fica None em vez de mascarar a falha com a metade do valor.
        det = self.det_judge.evaluate(sample.input, sample.expected_output, actual_output)
        det_overall = sum(det.values()) / len(det)
        combined = (det_overall + llm_score_val) / 2 if llm_score_val is not None else None
        return EvaluationResult(
            run_id=run.id,
            sample_id=sample.id,
            actual_output=actual_output,
            score_fidelity=det["score_fidelity"],
            score_coherence=det["score_coherence"],
            score_instruction=det["score_instruction"],
            score_overall=combined,
            judge_reasoning=reasoning,
        )

    async def _call_model(self, model: str, prompt: str) -> str:
        """POST /v1/chat/completions no gateway (com retry); retorna o content."""
        response = await post_with_retry(
            self.llm_judge.client,
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.settings.GATEWAY_API_KEY}"},
            json_body={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        return str(response.json()["choices"][0]["message"]["content"])
