// Página de avaliações: disparar evaluation runs + histórico de runs.
// Dados: POST/GET /v1/evaluations.
import RunEvaluation from '../components/RunEvaluation'

export default function Evaluations() {
  // TODO: listar runs (GET /v1/evaluations) com status e link para resultados.
  return (
    <div>
      <h1>Evaluations</h1>
      <RunEvaluation onStarted={() => undefined} />
      {/* lista de runs: id, dataset, model, judge_type, status */}
    </div>
  )
}
