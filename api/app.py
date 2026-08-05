"""
FastAPI application factory for Project Cinderella.

Usage
-----
    uvicorn api.app:app --reload --port 8000

Or via the CLI:
    python -m scripts.serve
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import books, dashboard, system


def create_app() -> FastAPI:
    app = FastAPI(
        title="Project Cinderella",
        description="Bloomberg Terminal for indie publishing breakout detection",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    app.include_router(dashboard.router)
    app.include_router(system.router)
    app.include_router(books.router)

    return app


app = create_app()
