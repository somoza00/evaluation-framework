// Página de datasets: lista (nome, descrição, samples) + New Dataset (DatasetUpload)
// + Evaluate por dataset (RunEvaluation com dataset pré-selecionado).

import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import type { DatasetResponse } from '../api'
import DatasetUpload from '../components/DatasetUpload'
import RunEvaluation from '../components/RunEvaluation'

export interface DatasetsProps {
  /** Callback para navegar para a página de resultados com uma run. */
  onRunStarted?: (runId: string) => void
}

const styles = {
  table: { borderCollapse: 'collapse' as const, width: '100%', marginTop: 12 },
  cell: { border: '1px solid #ccc', padding: '4px 8px', fontSize: 13 },
  header: { border: '1px solid #ccc', padding: '4px 8px', background: '#eee' },
  error: { color: '#c00', fontWeight: 'bold' as const },
}

export default function Datasets({ onRunStarted }: DatasetsProps) {
  const [datasets, setDatasets] = useState<DatasetResponse[]>([])
  const [showUpload, setShowUpload] = useState(false)
  const [evaluatingId, setEvaluatingId] = useState<string | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    api
      .listDatasets()
      .then(setDatasets)
      .catch((e) => setError(e instanceof Error ? e.message : 'erro ao listar datasets'))
  }, [])

  useEffect(load, [load])

  return (
    <div>
      <h1>Datasets</h1>
      <button type="button" onClick={() => setShowUpload(!showUpload)}>
        {showUpload ? 'Fechar' : 'New Dataset'}
      </button>

      {showUpload && (
        <DatasetUpload
          onUploaded={() => {
            setShowUpload(false)
            load()
          }}
        />
      )}

      {error && <p style={styles.error}>erro: {error}</p>}

      <table style={styles.table}>
        <thead>
          <tr>
            <th style={styles.header}>nome</th>
            <th style={styles.header}>descrição</th>
            <th style={styles.header}>samples</th>
            <th style={styles.header}>ações</th>
          </tr>
        </thead>
        <tbody>
          {datasets.map((d) => (
            <tr key={d.id}>
              <td style={styles.cell}>{d.name}</td>
              <td style={styles.cell}>{d.description || '—'}</td>
              <td style={styles.cell}>{d.samples_count}</td>
              <td style={styles.cell}>
                <button type="button" onClick={() => setEvaluatingId(d.id)}>
                  Evaluate
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {evaluatingId && (
        <div style={{ marginTop: 16 }}>
          <h3>Evaluate dataset</h3>
          <RunEvaluation
            datasetId={evaluatingId}
            onStarted={(runId) => {
              setEvaluatingId(null)
              onRunStarted?.(runId)
            }}
          />
        </div>
      )}
    </div>
  )
}
