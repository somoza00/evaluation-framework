"""Entrypoint da aplicação FastAPI do evaluation-framework."""

from fastapi import FastAPI

from app.api.v1 import api_router

app = FastAPI(
    title="Evaluation Framework API",
    description="Avaliação de modelos LLM: datasets, evaluation runs e judges.",
    version="0.1.0",
)

# TODO: CORS (origem http://localhost:5174) e lifespan (healthcheck) quando implementados.

app.include_router(api_router, prefix="/v1")
