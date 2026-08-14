// Página de resultados: ResultsTable do runId atual (lido da URL ?run=...)
// + Compare: seleciona outras runs e renderiza ModelComparison (BarChart).

import { useState } from 'react'
import ModelComparison from '../components/ModelComparison'
import ResultsTable from '../components/ResultsTable'

export interface ResultsProps {
  /** ID da run exibida (espelhado na query string ?run=). */
  runId: string
}

const styles = {
  compareBox: { marginTop: 24, border: '1px solid #ccc', padding: 12 },
  input: { width: 300, padding: 4, marginRight: 8 },
}

export default function Results({ runId }: ResultsProps) {
  const [compareInput, setCompareInput] = useState('')
  const [compareIds, setCompareIds] = useState<string[]>([])

  function handleCompare() {
    const extra = compareInput
      .split(',')
      .map((id) => id.trim())
      .filter(Boolean)
    setCompareIds(extra)
  }

  return (
    <div>
      <h1>Results</h1>
      {runId ? (
        <ResultsTable runId={runId} />
      ) : (
        <p>Nenhuma run selecionada — rode uma avaliação ou clique em uma run na aba Evaluations.</p>
      )}

      <div style={styles.compareBox}>
        <h3>Comparar com outra run</h3>
        <input
          style={styles.input}
          value={compareInput}
          onChange={(e) => setCompareInput(e.target.value)}
          placeholder="id1,id2 (separados por vírgula)"
        />
        <button type="button" onClick={handleCompare}>
          Compare
        </button>
        {compareIds.length > 0 && runId && (
          <ModelComparison runIds={[runId, ...compareIds]} />
        )}
      </div>
    </div>
  )
}
