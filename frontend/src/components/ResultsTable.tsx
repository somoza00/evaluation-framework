// Tabela de resultados de uma run: input/expected/actual truncados, scores e reasoning.
// Dados: GET /v1/results/{run_id}. Linha expansível ao clicar mostra o texto completo.

import { useEffect, useState } from 'react'
import { api } from '../api'
import type { ResultItem } from '../api'

export interface ResultsTableProps {
  /** ID da evaluation run cujos resultados serão exibidos. */
  runId: string
}

const styles = {
  table: { borderCollapse: 'collapse' as const, width: '100%' },
  cell: { border: '1px solid #ccc', padding: '4px 8px', fontSize: 13 },
  header: { border: '1px solid #ccc', padding: '4px 8px', background: '#eee' },
  error: { color: '#c00', fontWeight: 'bold' as const },
}

const MAX_LEN = 40

function truncate(text: string): string {
  return text.length > MAX_LEN ? `${text.slice(0, MAX_LEN)}…` : text
}

function formatScore(value: number | null): string {
  return value === null ? '—' : value.toFixed(2)
}

export default function ResultsTable({ runId }: ResultsTableProps) {
  const [results, setResults] = useState<ResultItem[]>([])
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    api
      .getResults(runId)
      .then((payload) => {
        if (!cancelled) setResults(payload.results)
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'erro ao buscar resultados')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [runId])

  if (loading) return <p>carregando resultados…</p>
  if (error) return <p style={styles.error}>erro: {error}</p>
  if (results.length === 0) return <p>nenhum resultado para esta run.</p>

  return (
    <table style={styles.table}>
      <thead>
        <tr>
          <th style={styles.header}>input</th>
          <th style={styles.header}>expected</th>
          <th style={styles.header}>actual</th>
          <th style={styles.header}>fidelity</th>
          <th style={styles.header}>coherence</th>
          <th style={styles.header}>instruction</th>
          <th style={styles.header}>overall</th>
          <th style={styles.header}>reasoning</th>
        </tr>
      </thead>
      <tbody>
        {results.map((r) => (
          <ResultRow
            key={r.id}
            result={r}
            expanded={expandedId === r.id}
            onToggle={() => setExpandedId(expandedId === r.id ? null : r.id)}
          />
        ))}
      </tbody>
    </table>
  )
}

function ResultRow({
  result,
  expanded,
  onToggle,
}: {
  result: ResultItem
  expanded: boolean
  onToggle: () => void
}) {
  return (
    <>
      <tr onClick={onToggle} style={{ cursor: 'pointer' }}>
        <td style={styles.cell}>{truncate(result.input ?? '—')}</td>
        <td style={styles.cell}>{truncate(result.expected_output ?? '—')}</td>
        <td style={styles.cell}>{truncate(result.actual_output)}</td>
        <td style={styles.cell}>{formatScore(result.score_fidelity)}</td>
        <td style={styles.cell}>{formatScore(result.score_coherence)}</td>
        <td style={styles.cell}>{formatScore(result.score_instruction)}</td>
        <td style={styles.cell}>{formatScore(result.score_overall)}</td>
        <td style={styles.cell}>{truncate(result.judge_reasoning ?? '—')}</td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={8} style={{ ...styles.cell, background: '#fafafa' }}>
            <strong>input:</strong> {result.input ?? '—'}
            <br />
            <strong>expected:</strong> {result.expected_output ?? '—'}
            <br />
            <strong>actual:</strong> {result.actual_output}
            <br />
            <strong>reasoning:</strong> {result.judge_reasoning ?? '—'}
          </td>
        </tr>
      )}
    </>
  )
}
