// Página de datasets: upload de novos datasets + listagem dos existentes.
// Dados: GET /v1/datasets e POST /v1/datasets.
import DatasetUpload from '../components/DatasetUpload'

export default function Datasets() {
  // TODO: listar datasets (GET /v1/datasets) e renderizar como cards/linhas.
  return (
    <div>
      <h1>Datasets</h1>
      <DatasetUpload onUploaded={() => undefined} />
      {/* lista de datasets */}
    </div>
  )
}
