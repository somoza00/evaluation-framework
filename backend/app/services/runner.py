"""Runner: orquestra a avaliação de uma EvaluationRun de ponta a ponta."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.dataset import Sample
from app.models.evaluation import (
    EvaluationResult,
    EvaluationRun,
    JudgeType,
    RunStatus,
)
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

    async def run(self, run_id: uuid.UUID) -> None:
        """Executa uma run completa: pending -> running -> done (ou failed).

        1. Busca EvaluationRun, seta status=RUNNING e commita
        2. Busca todos os Samples do dataset associado
        3. Para cada Sample: chama o modelo avaliado via gateway, roda o judge
           conforme run.judge_type e persiste um EvaluationResult
        4. Seta status=DONE + finished_at e commita
        5. Em exceção: seta status=FAILED, commita e re-levanta
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

            for sample in samples:
                actual_output = await self._call_model(run.model, sample.input)
                result = await self._build_result(run, sample, actual_output)
                self.session.add(result)

            run.status = RunStatus.DONE
            # utcnow() é deprecated; a coluna é naive (sem timezone, ver Fase 2),
            # então geramos UTC "de verdade" e removemos o tzinfo antes de gravar.
            run.finished_at = datetime.now(UTC).replace(tzinfo=None)
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
        if run.judge_type == JudgeType.LLM:
            return EvaluationResult(
                run_id=run.id,
                sample_id=sample.id,
                actual_output=actual_output,
                score_overall=float(llm["score_overall"]),
                judge_reasoning=str(llm["judge_reasoning"]),
            )

        # BOTH: combina scores parciais do determinístico com o overall do LLM.
        det = self.det_judge.evaluate(sample.input, sample.expected_output, actual_output)
        det_overall = sum(det.values()) / len(det)
        return EvaluationResult(
            run_id=run.id,
            sample_id=sample.id,
            actual_output=actual_output,
            score_fidelity=det["score_fidelity"],
            score_coherence=det["score_coherence"],
            score_instruction=det["score_instruction"],
            score_overall=(det_overall + float(llm["score_overall"])) / 2,
            judge_reasoning=str(llm["judge_reasoning"]),
        )

    async def _call_model(self, model: str, prompt: str) -> str:
        """POST /v1/chat/completions no gateway; retorna o content da resposta."""
        response = await self.llm_judge.client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.settings.GATEWAY_API_KEY}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        response.raise_for_status()
        return str(response.json()["choices"][0]["message"]["content"])
