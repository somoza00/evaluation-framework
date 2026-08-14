// Página de resultados: tabela de uma run + comparação entre runs.
// Dados: GET /v1/results/{run_id} e GET /v1/results/compare?runs=...
import ModelComparison from '../components/ModelComparison'
import ResultsTable from '../components/ResultsTable'

export default function Results() {
  // TODO: seleção de run(s) e carregamento dos dados de resultados.
  return (
    <div>
      <h1>Results</h1>
      <ResultsTable runId="" />
      <ModelComparison runIds={[]} />
    </div>
  )
}
