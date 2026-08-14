// Formulário para disparar uma evaluation run.
// Select de dataset (GET /v1/datasets), input de model e select de judge_type.
// POST /v1/evaluations -> 202; onStarted(runId) navega para os resultados.

import { useEffect, useState } from 'react'
import { api } from '../api'
import type { DatasetResponse, JudgeType } from '../api'

export interface RunEvaluationProps {
  /** Dataset pré-selecionado (opcional: permite rodar sem sair da página). */
  datasetId?: string
  /** Callback disparado após a run ser criada, com o id da run. */
  onStarted?: (runId: string) => void
}

const styles = {
  field: { marginBottom: 8, display: 'block' as const },
  input: { width: '100%', padding: 4 },
  error: { color: '#c00', fontWeight: 'bold' as const },
  info: { color: '#333', fontWeight: 'bold' as const },
}

export default function RunEvaluation({ datasetId, onStarted }: RunEvaluationProps) {
  const [datasets, setDatasets] = useState<DatasetResponse[]>([])
  const [selected, setSelected] = useState(datasetId ?? '')
  const [model, setModel] = useState('openai/gpt-4o')
  const [judgeType, setJudgeType] = useState<JudgeType>('llm')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')

  useEffect(() => {
    api
      .listDatasets()
      .then((data) => {
        setDatasets(data)
        if (!selected && data.length > 0) setSelected(data[0].id)
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'erro ao listar datasets'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (datasetId) setSelected(datasetId)
  }, [datasetId])

  async function handleRun() {
    if (!selected) {
      setError('selecione um dataset')
      return
    }
    if (!model.trim()) {
      setError('informe o model (ex: openai/gpt-4o)')
      return
    }
    setLoading(true)
    setError('')
    setInfo('')
    try {
      const run = await api.createEvaluation({
        dataset_id: selected,
        model: model.trim(),
        judge_type: judgeType,
      })
      setInfo(`run ${run.id.slice(0, 8)} criada — redirecionando para os resultados…`)
      onStarted?.(run.id)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'erro ao criar a run')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <label style={styles.field}>
        Dataset
        <select style={styles.input} value={selected} onChange={(e) => setSelected(e.target.value)}>
          {datasets.length === 0 && <option value="">— nenhum dataset —</option>}
          {datasets.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name} ({d.samples_count} samples)
            </option>
          ))}
        </select>
      </label>
      <label style={styles.field}>
        Model
        <input
          style={styles.input}
          value={model}
          onChange={(e) => setModel(e.target.value)}
          placeholder="openai/gpt-4o"
        />
      </label>
      <label style={styles.field}>
        Judge type
        <select style={styles.input} value={judgeType} onChange={(e) => setJudgeType(e.target.value as JudgeType)}>
          <option value="deterministic">deterministic</option>
          <option value="llm">llm</option>
          <option value="both">both</option>
        </select>
      </label>
      <button type="button" onClick={handleRun} disabled={loading}>
        {loading ? 'Rodando…' : 'Run'}
      </button>
      {error && <p style={styles.error}>{error}</p>}
      {info && <p style={styles.info}>{info}</p>}
    </div>
  )
}
