// Formulário de upload de dataset: nome, descrição e arquivo de samples (CSV ou JSON).
// CSV esperado: colunas `input,expected_output`. JSON esperado: array de {input, expected_output}.
// Fluxo: POST /v1/datasets -> POST /v1/datasets/{id}/samples (bulk).
// Feedback visual: loading, sucesso, erro.

import { useState } from 'react'
import type { FormEvent } from 'react'
import { api } from '../api'
import type { SampleCreate } from '../api'

export interface DatasetUploadProps {
  /** Callback disparado após o upload concluir com sucesso. */
  onUploaded?: () => void
}

type Status = 'idle' | 'loading' | 'success' | 'error'

const styles = {
  field: { marginBottom: 8, display: 'block' as const },
  input: { width: '100%', padding: 4 },
  message: (status: Status) => ({
    marginTop: 8,
    fontWeight: 'bold' as const,
    color: status === 'error' ? '#c00' : status === 'success' ? '#080' : '#333',
  }),
}

// CSV: uma linha por sample, `input,expected_output` (cabeçalho opcional).
function parseCsv(text: string): SampleCreate[] {
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
  const hasHeader = lines[0]?.toLowerCase().startsWith('input')
  const body = hasHeader ? lines.slice(1) : lines
  return body
    .map((line) => {
      const comma = line.indexOf(',')
      if (comma === -1) return null
      return {
        input: line.slice(0, comma).trim(),
        expected_output: line.slice(comma + 1).trim(),
      }
    })
    .filter((s): s is SampleCreate => s !== null && s.input !== '' && s.expected_output !== '')
}

// JSON: array de {input, expected_output} (com metadata opcional).
function parseJson(text: string): SampleCreate[] {
  const data: unknown = JSON.parse(text)
  if (!Array.isArray(data)) throw new Error('JSON deve ser um array de {input, expected_output}')
  return data
    .filter(
      (item): item is SampleCreate =>
        typeof item === 'object' &&
        item !== null &&
        typeof (item as SampleCreate).input === 'string' &&
        typeof (item as SampleCreate).expected_output === 'string',
    )
    .map((item) => ({
      input: (item as SampleCreate).input,
      expected_output: (item as SampleCreate).expected_output,
    }))
}

async function parseFile(file: File): Promise<SampleCreate[]> {
  const text = await file.text()
  if (file.name.toLowerCase().endsWith('.csv')) return parseCsv(text)
  return parseJson(text)
}

export default function DatasetUpload({ onUploaded }: DatasetUploadProps) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [status, setStatus] = useState<Status>('idle')
  const [message, setMessage] = useState('')

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!name.trim() || !file) {
      setStatus('error')
      setMessage('preencha o nome e selecione um arquivo (CSV ou JSON)')
      return
    }
    setStatus('loading')
    setMessage('enviando…')
    try {
      const samples = await parseFile(file)
      if (samples.length === 0) throw new Error('arquivo sem samples válidos')
      const dataset = await api.createDataset(name.trim(), description.trim())
      await api.addSamples(dataset.id, samples)
      setStatus('success')
      setMessage(`dataset "${dataset.name}" criado com ${samples.length} samples`)
      setName('')
      setDescription('')
      setFile(null)
      onUploaded?.()
    } catch (error) {
      setStatus('error')
      setMessage(error instanceof Error ? error.message : 'erro no upload')
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <label style={styles.field}>
        Nome *
        <input
          style={styles.input}
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="ex: customer-support-pt"
        />
      </label>
      <label style={styles.field}>
        Descrição
        <textarea
          style={styles.input}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
        />
      </label>
      <label style={styles.field}>
        Arquivo de samples (CSV: input,expected_output | JSON: array)
        <input
          type="file"
          accept=".csv,.json,.txt"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </label>
      <button type="submit" disabled={status === 'loading'}>
        {status === 'loading' ? 'Enviando…' : 'Upload'}
      </button>
      {message && <p style={styles.message(status)}>{message}</p>}
    </form>
  )
}
