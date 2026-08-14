"""Runner: orquestra a execução de uma evaluation run de ponta a ponta."""

from app.models.evaluation import EvaluationRun


class EvaluationRunner:
    """Coordena judges + persistência de EvaluationResult para uma run."""

    def __init__(self, run: EvaluationRun) -> None:
        """Armazena a run alvo da execução."""

    async def run(self) -> None:
        """Executa a run: itera samples, chama judge(s) e persiste resultados.

        Transições de status: pending -> running -> done (ou failed).
        """
