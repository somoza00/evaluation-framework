"""Testes dos endpoints de results: médias, ordem e dedupe no compare."""

import csv
import io
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.results import _CSV_COLUMNS
from app.models.evaluation import EvaluationResult, EvaluationRun, JudgeType, RunStatus


async def _make_run(db_session: AsyncSession, dataset_id: str) -> str:
    """Insere uma EvaluationRun direto no banco (sem disparar o runner)."""
    run_id = uuid.uuid4()
    db_session.add(
        EvaluationRun(
            id=run_id,
            dataset_id=uuid.UUID(dataset_id),
            model="m",
            judge_type=JudgeType.DETERMINISTIC,
            status=RunStatus.DONE,
        )
    )
    await db_session.commit()
    return str(run_id)


async def test_averages_cover_all_results_not_just_page(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /v1/results/{run_id}?limit=1 calcula médias sobre TODA a run, não só a página."""
    created = await client.post("/v1/datasets", json={"name": "ds", "description": ""})
    dataset_id = created.json()["id"]

    samples = await client.post(
        f"/v1/datasets/{dataset_id}/samples",
        json=[{"input": f"q{i}", "expected_output": f"a{i}"} for i in range(3)],
    )
    sample_ids = samples.json()["ids"]

    run_id = await _make_run(db_session, dataset_id)

    scores = [0.2, 0.5, 0.8]
    for sid, score in zip(sample_ids, scores):
        db_session.add(
            EvaluationResult(
                run_id=uuid.UUID(run_id),
                sample_id=uuid.UUID(sid),
                actual_output="x",
                score_overall=score,
            )
        )
    await db_session.commit()

    response = await client.get(f"/v1/results/{run_id}", params={"limit": 1})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 3
    assert body["count"] == 1  # página de 1
    # Média de toda a run, não da página
    assert body["averages"]["score_overall"] == pytest.approx(sum(scores) / len(scores))


async def test_results_include_sample_input_and_expected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /v1/results/{run_id} inclui input/expected_output do sample (tabela do FE)."""
    created = await client.post("/v1/datasets", json={"name": "ds", "description": ""})
    dataset_id = created.json()["id"]
    samples = await client.post(
        f"/v1/datasets/{dataset_id}/samples",
        json=[{"input": "pergunta X", "expected_output": "resposta X"}],
    )
    sample_ids = samples.json()["ids"]

    run_id = await _make_run(db_session, dataset_id)
    db_session.add(
        EvaluationResult(
            run_id=uuid.UUID(run_id),
            sample_id=uuid.UUID(sample_ids[0]),
            actual_output="resposta do modelo",
            score_overall=0.9,
        )
    )
    await db_session.commit()

    response = await client.get(f"/v1/results/{run_id}")
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["input"] == "pergunta X"
    assert result["expected_output"] == "resposta X"


async def test_compare_respects_requested_order(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /v1/results/compare?runs=B,A,C devolve [B,A,C], na ordem pedida."""
    created = await client.post("/v1/datasets", json={"name": "ds", "description": ""})
    dataset_id = created.json()["id"]

    run_ids: list[str] = []
    for _ in range(3):
        run_ids.append(await _make_run(db_session, dataset_id))

    requested = [run_ids[1], run_ids[0], run_ids[2]]
    response = await client.get("/v1/results/compare", params={"runs": ",".join(requested)})
    assert response.status_code == 200, response.text
    got = [r["run_id"] for r in response.json()["runs"]]
    assert got == requested


async def test_compare_deduplicates_duplicate_run_ids(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """runs=<id>,<id> não deve dar 404 falso: IDs duplicados são despulados."""
    created = await client.post("/v1/datasets", json={"name": "ds", "description": ""})
    dataset_id = created.json()["id"]
    run_id = await _make_run(db_session, dataset_id)

    response = await client.get("/v1/results/compare", params={"runs": f"{run_id},{run_id}"})
    assert response.status_code == 200, response.text
    got = [r["run_id"] for r in response.json()["runs"]]
    assert got == [run_id]


async def test_results_ordered_by_created_at(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Resultados saem na ordem de created_at (ordem de avaliação), não do id (uuid4)."""
    from datetime import UTC, datetime

    created = await client.post("/v1/datasets", json={"name": "ds-ord", "description": ""})
    dataset_id = created.json()["id"]
    sample_ids = (
        await client.post(
            f"/v1/datasets/{dataset_id}/samples",
            json=[{"input": f"q{i}", "expected_output": f"a{i}"} for i in range(3)],
        )
    ).json()["ids"]
    run_id = await _make_run(db_session, dataset_id)

    base = datetime(2026, 1, 1, tzinfo=UTC).replace(tzinfo=None)
    plan = [(sample_ids[0], base.replace(microsecond=2), "segundo"),
            (sample_ids[1], base.replace(microsecond=1), "primeiro"),
            (sample_ids[2], base.replace(microsecond=3), "terceiro")]
    for sid, ts, out in plan:
        db_session.add(
            EvaluationResult(
                run_id=uuid.UUID(run_id), sample_id=uuid.UUID(sid),
                actual_output=out, score_overall=0.5, created_at=ts,
            )
        )
    await db_session.commit()

    got = (await client.get(f"/v1/results/{run_id}")).json()["results"]
    assert [r["actual_output"] for r in got] == ["primeiro", "segundo", "terceiro"]


async def test_export_csv_traz_todas_as_samples_com_scores(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /v1/results/{run_id}/export devolve a run inteira em CSV (download)."""
    created = await client.post("/v1/datasets", json={"name": "ds-export", "description": ""})
    dataset_id = created.json()["id"]
    samples = await client.post(
        f"/v1/datasets/{dataset_id}/samples",
        json=[
            {"input": "q0", "expected_output": "a0"},
            # vírgula e quebra de linha: o CSV precisa citar/quebrar corretamente
            {"input": 'q1, com vírgula', "expected_output": "linha1\nlinha2"},
        ],
    )
    sample_ids = samples.json()["ids"]
    run_id = await _make_run(db_session, dataset_id)

    db_session.add(
        EvaluationResult(
            run_id=uuid.UUID(run_id),
            sample_id=uuid.UUID(sample_ids[0]),
            actual_output="resposta ok",
            score_overall=0.5,
            score_fidelity=1.0,
            score_coherence=0.5,
            score_instruction=0.0,
            judge_reasoning="parece bom",
        )
    )
    # Judge falhou nesta sample: score None tem de sair como célula VAZIA
    # (0,0 seria uma nota legítima e falsearia a média na planilha).
    db_session.add(
        EvaluationResult(
            run_id=uuid.UUID(run_id),
            sample_id=uuid.UUID(sample_ids[1]),
            actual_output="",
            score_overall=None,
            judge_reasoning="erro ao avaliar via LLM",
        )
    )
    await db_session.commit()

    response = await client.get(f"/v1/results/{run_id}/export")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert run_id in response.headers["content-disposition"]

    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0] == list(_CSV_COLUMNS)
    assert len(rows) == 3  # cabeçalho + 2 samples

    first = dict(zip(_CSV_COLUMNS, rows[1], strict=True))
    assert first["sample_id"] == sample_ids[0]
    assert first["input"] == "q0"
    assert first["expected_output"] == "a0"
    assert first["actual_output"] == "resposta ok"
    assert first["score_overall"] == "0.5000"
    assert first["score_fidelity"] == "1.0000"
    assert first["judge_reasoning"] == "parece bom"

    second = dict(zip(_CSV_COLUMNS, rows[2], strict=True))
    assert second["input"] == "q1, com vírgula"  # vírgula preservada pelo quoting
    assert second["expected_output"] == "linha1\nlinha2"
    assert second["score_overall"] == ""
    assert second["score_fidelity"] == ""


async def test_export_csv_returns_404_for_unknown_run(client: AsyncClient) -> None:
    response = await client.get(f"/v1/results/{uuid.uuid4()}/export")
    assert response.status_code == 404


async def test_export_csv_of_empty_run_is_header_only(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Run sem resultados ainda exporta o cabeçalho (planilha vazia, não erro)."""
    created = await client.post("/v1/datasets", json={"name": "ds-vazio", "description": ""})
    run_id = await _make_run(db_session, created.json()["id"])

    response = await client.get(f"/v1/results/{run_id}/export")
    assert response.status_code == 200, response.text
    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows == [list(_CSV_COLUMNS)]
