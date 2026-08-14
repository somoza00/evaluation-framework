// Formulário de upload de dataset: nome, descrição e arquivo de samples (JSONL).
// Fluxo: POST /v1/datasets (name, description) -> POST /v1/datasets/{id}/samples.

export interface DatasetUploadProps {
  /** Callback disparado após o upload concluir com sucesso. */
  onUploaded?: () => void
}

export default function DatasetUpload({ onUploaded }: DatasetUploadProps) {
  // TODO: inputs (name, description), file input (.jsonl), fetch e onUploaded().
  return (
    <div>
      {/* form: name, description, arquivo de samples (JSONL) */}
    </div>
  )
}
