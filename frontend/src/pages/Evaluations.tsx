// Página de avaliações: lista de runs (model, judge_type, status, progresso).
// Auto-refresh a cada 5s enquanto houver run com status=running.
// Clique na run navega para a página de resultados.

import { useEffect, useState } from 'react'
import { api } from '../api'
import type { RunResponse } from '../api'

export interface EvaluationsProps {
  /** Callback para navegar para a página de resultados com uma run. */
  onRunStarted?: (runId: string) => void
}

const REFRESH_MS = 5000

const styles = {
  table: { borderCollapse: 'collapse' as const, width: '100%', marginTop: 12 },
  cell: { border: '1px solid #ccc', padding: '4px 8px', fontSize: 13 },
  header: { border: '1px solid #ccc', padding: '4px 8px', background: '#eee' },
  error: { color: '#c00', fontWeight: 'bold' as const },
  track: { background: '#eee', borderRadius: 4, height: 12, width: 120 },
  bar: (progress: number) => ({
    background: progress >= 1 ? '#16a34a' : '#2563eb',
    borderRadius: 4,
    height: 12,
    width: `${Math.round(progress * 100)}%`,
  }),
}

export default function Evaluations({ onRunStarted }: EvaluationsProps) {
  const [runs, setRuns] = useState<RunResponse[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    let timer: number | undefined

    async function load() {
      try {
        const data = await api.listEvaluations()
        if (cancelled) return
        setRuns(data)
        // agenda o próximo refresh enquanto houver run que ainda não terminou
        // (pending inclusa: o background task pode não ter marcado running ainda)
        if (data.some((run) => run.status === 'running' || run.status === 'pending')) {
          timer = window.setTimeout(load, REFRESH_MS)
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'erro ao listar runs')
      }
    }

    load()
    return () => {
      cancelled = true
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [])

  return (
    <div>
      <h1>Evaluations</h1>
      {error && <p style={styles.error}>erro: {error}</p>}
      <table style={styles.table}>
        <thead>
          <tr>
            <th style={styles.header}>model</th>
            <th style={styles.header}>judge_type</th>
            <th style={styles.header}>status</th>
            <th style={styles.header}>progresso</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr
              key={run.id}
              onClick={() => onRunStarted?.(run.id)}
              style={{ cursor: 'pointer' }}
            >
              <td style={styles.cell}>{run.model}</td>
              <td style={styles.cell}>{run.judge_type}</td>
              <td style={styles.cell}>{run.status}</td>
              <td style={styles.cell}>
                <div style={styles.track}>
                  <div style={styles.bar(run.progress)} />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {runs.length === 0 && <p>nenhuma run ainda.</p>}
    </div>
  )
}
