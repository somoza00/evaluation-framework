// Comparação entre runs: gráfico (Recharts) com scores agregados por run/model.
// Dados: GET /v1/results/compare?runs=id1,id2,...

export interface ModelComparisonProps {
  /** IDs das runs a comparar (2+ para o gráfico fazer sentido). */
  runIds: string[]
}

export default function ModelComparison({ runIds }: ModelComparisonProps) {
  // TODO: fetch compare, montar dados para Recharts (BarChart) e renderizar.
  return (
    <div>
      {/* Recharts: BarChart com média de score_* por run/model */}
    </div>
  )
}
