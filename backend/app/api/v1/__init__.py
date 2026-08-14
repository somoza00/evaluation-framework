"""API v1 — montagem central dos routers (prefixo /v1 aplicado no main.py)."""

from fastapi import APIRouter

from app.api.v1 import datasets, evaluations, results

api_router = APIRouter()
api_router.include_router(datasets.router)
api_router.include_router(evaluations.router)
api_router.include_router(results.router)
