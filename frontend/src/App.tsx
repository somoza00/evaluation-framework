// Shell da aplicação: navbar com abas (Datasets | Evaluations | Results).
// Roteamento simples com useState (sem react-router); o runId atual é
// espelhado na query string (?run=...) via history.replaceState.

import { useEffect, useState } from 'react'
import Datasets from './pages/Datasets'
import Evaluations from './pages/Evaluations'
import Results from './pages/Results'

type Tab = 'datasets' | 'evaluations' | 'results'

const styles = {
  nav: { display: 'flex' as const, gap: 8, padding: '8px 0', borderBottom: '1px solid #ccc' },
  active: { fontWeight: 'bold' as const },
}

function readRunFromUrl(): string {
  return new URLSearchParams(window.location.search).get('run') ?? ''
}

export default function App() {
  const [tab, setTab] = useState<Tab>('datasets')
  const [runId, setRunId] = useState(readRunFromUrl)

  // sincroniza o runId exibido quando a URL muda (back/forward)
  useEffect(() => {
    const onPopState = () => setRunId(readRunFromUrl())
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  function openRun(id: string) {
    setRunId(id)
    setTab('results')
    window.history.replaceState(null, '', `?run=${id}`)
  }

  return (
    <div>
      <nav style={styles.nav}>
        <button style={tab === 'datasets' ? styles.active : undefined} onClick={() => setTab('datasets')}>
          Datasets
        </button>
        <button style={tab === 'evaluations' ? styles.active : undefined} onClick={() => setTab('evaluations')}>
          Evaluations
        </button>
        <button style={tab === 'results' ? styles.active : undefined} onClick={() => setTab('results')}>
          Results
        </button>
      </nav>
      {tab === 'datasets' && <Datasets onRunStarted={openRun} />}
      {tab === 'evaluations' && <Evaluations onRunStarted={openRun} />}
      {tab === 'results' && <Results runId={runId} />}
    </div>
  )
}
