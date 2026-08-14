// Shell da aplicação: navegação por abas entre as três páginas.
import { useState } from 'react'
import Datasets from './pages/Datasets'
import Evaluations from './pages/Evaluations'
import Results from './pages/Results'

type Tab = 'datasets' | 'evaluations' | 'results'

export default function App() {
  const [tab, setTab] = useState<Tab>('datasets')

  return (
    <div>
      <nav>
        <button onClick={() => setTab('datasets')}>Datasets</button>
        <button onClick={() => setTab('evaluations')}>Evaluations</button>
        <button onClick={() => setTab('results')}>Results</button>
      </nav>
      {tab === 'datasets' && <Datasets />}
      {tab === 'evaluations' && <Evaluations />}
      {tab === 'results' && <Results />}
    </div>
  )
}
