// Tabela de resultados de uma run: actual_output, scores e judge_reasoning.
// Dados: GET /v1/results/{run_id}.

export interface ResultsTableProps {
  /** ID da evaluation run cujos resultados serão exibidos. */
  runId: string
}

export default function ResultsTable({ runId }: ResultsTableProps) {
  // TODO: fetch GET /v1/results/{runId} e renderizar uma EvaluationResult por linha.
  return (
    <div data-run-id={runId}>
      {/* tabela: sample, actual_output, score_fidelity, score_coherence,
          score_instruction, score_overall, judge_reasoning */}
    </div>
  )
}
