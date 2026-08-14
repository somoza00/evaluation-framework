// Formulário para disparar uma evaluation run.
// Fluxo: POST /v1/evaluations (dataset_id, model, judge_type).

export interface RunEvaluationProps {
  /** Dataset pré-selecionado (opcional: permite rodar sem sair da página). */
  datasetId?: string
  /** Callback disparado após a run ser criada, com o id da run. */
  onStarted?: (runId: string) => void
}

export default function RunEvaluation({ datasetId, onStarted }: RunEvaluationProps) {
  // TODO: inputs (model, judge_type), fetch POST /v1/evaluations, onStarted(runId).
  return (
    <div>
      {/* form: model, judge_type (deterministic | llm | both) */}
    </div>
  )
}
