// Tipos das respostas da API + helpers fetch (fetch nativo, sem axios).
// Base relativa: o vite dev server faz proxy de /v1 para o backend (:8001).

export interface DatasetResponse {
  id: string
  name: string
  description: string
  created_at: string
  samples_count: number
}

export type JudgeType = 'deterministic' | 'llm' | 'both'
export type RunStatus = 'pending' | 'running' | 'done' | 'failed'

export interface RunResponse {
  id: string
  dataset_id: string
  model: string
  judge_type: JudgeType
  status: RunStatus
  created_at: string
  finished_at: string | null
  progress: number
}

export interface SampleCreate {
  input: string
  expected_output: string
  metadata?: Record<string, unknown>
}

export interface ResultItem {
  id: string
  sample_id: string
  actual_output: string
  score_fidelity: number | null
  score_coherence: number | null
  score_instruction: number | null
  score_overall: number | null
  judge_reasoning: string | null
  // O backend ainda não inclui input/expected por result; quando incluir,
  // estes campos passam a ser preenchidos (a tabela mostra "—" enquanto isso).
  input?: string
  expected_output?: string
}

export interface ResultsPayload {
  run_id: string
  count: number
  averages: Record<string, number | null>
  results: ResultItem[]
}

export interface CompareEntry {
  run_id: string
  model: string
  judge_type: JudgeType
  status: RunStatus
  averages: Record<string, number | null>
}

export interface ComparePayload {
  runs: CompareEntry[]
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })
  if (!response.ok) {
    const body = await response.text().catch(() => '')
    throw new Error(`API ${response.status}${body ? `: ${body.slice(0, 200)}` : ''}`)
  }
  return response.json() as Promise<T>
}

export const api = {
  listDatasets: () => request<DatasetResponse[]>('/v1/datasets'),

  createDataset: (name: string, description: string) =>
    request<DatasetResponse>('/v1/datasets', {
      method: 'POST',
      body: JSON.stringify({ name, description }),
    }),

  addSamples: (datasetId: string, samples: SampleCreate[]) =>
    request<{ count: number; ids: string[] }>(`/v1/datasets/${datasetId}/samples`, {
      method: 'POST',
      body: JSON.stringify(samples),
    }),

  listEvaluations: () => request<RunResponse[]>('/v1/evaluations'),

  createEvaluation: (payload: { dataset_id: string; model: string; judge_type: JudgeType }) =>
    request<RunResponse>('/v1/evaluations', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  getResults: (runId: string) => request<ResultsPayload>(`/v1/results/${runId}`),

  compareRuns: (runIds: string[]) =>
    request<ComparePayload>(`/v1/results/compare?runs=${runIds.join(',')}`),
}
