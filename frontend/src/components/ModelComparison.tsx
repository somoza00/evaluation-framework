// Comparação entre runs: BarChart (Recharts) com scores médios por critério.
// Dados: GET /v1/results/compare?runs=id1,id2,... — uma cor por run, eixo X = critérios.

import { useEffect, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '../api'
import type { CompareEntry } from '../api'

export interface ModelComparisonProps {
  /** IDs das runs a comparar (2+ para o gráfico fazer sentido). */
  runIds: string[]
}

const CRITERIA = ['score_fidelity', 'score_coherence', 'score_instruction', 'score_overall'] as const

const PALETTE = ['#2563eb', '#16a34a', '#dc2626', '#d97706', '#7c3aed', '#0891b2']

const styles = {
  error: { color: '#c00', fontWeight: 'bold' as const },
}

type ChartRow = Record<string, string | number>

export default function ModelComparison({ runIds }: ModelComparisonProps) {
  const [entries, setEntries] = useState<CompareEntry[]>([])
  const [error, setError] = useState('')

  const key = runIds.join(',')

  useEffect(() => {
    if (runIds.length === 0) return
    let cancelled = false
    setError('')
    api
      .compareRuns(runIds)
      .then((payload) => {
        if (!cancelled) setEntries(payload.runs)
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'erro ao comparar runs')
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  if (runIds.length === 0) return <p>selecione 2+ runs para comparar.</p>
  if (error) return <p style={styles.error}>erro: {error}</p>

  // label único por run: model (run_id curto)
  const label = (entry: CompareEntry) => `${entry.model} (${entry.run_id.slice(0, 8)})`
  const data: ChartRow[] = CRITERIA.map((criterion) => {
    const row: ChartRow = { criterion: criterion.replace('score_', '') }
    entries.forEach((entry) => {
      row[label(entry)] = entry.averages[criterion] ?? 0
    })
    return row
  })

  return (
    <div>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="criterion" />
          <YAxis domain={[0, 1]} />
          <Tooltip />
          <Legend />
          {entries.map((entry, index) => (
            <Bar
              key={entry.run_id}
              dataKey={label(entry)}
              fill={PALETTE[index % PALETTE.length]}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
