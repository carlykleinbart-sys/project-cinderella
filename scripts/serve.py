"""
CLI to launch the Project Cinderella web dashboard.

Usage
-----
    python -m scripts.serve              # http://localhost:8000
    python -m scripts.serve --port 9000
    python -m scripts.serve --reload     # dev mode

Railway note: the PORT environment variable is respected automatically as
the default port so no extra configuration is needed on Railway.
"""
import os

import click
import uvicorn


def _default_port() -> int:
    """Return PORT env var (set by Railway/Render/Fly) or fall back to 8000."""
    return int(os.environ.get("PORT", 8000))


@click.command()
@click.option("--host", default="0.0.0.0", show_default=True, help="Bind address")
@click.option("--port", default=_default_port, show_default=True, help="Port to listen on (defaults to $PORT env var)")
@click.option("--reload", is_flag=True, default=False, help="Enable hot-reload (dev mode)")
@click.option("--workers", default=1, show_default=True, help="Number of worker processes")
def serve(host: str, port: int, reload: bool, workers: int) -> None:
    """Start the Cinderella web dashboard."""
    click.echo(f"Starting Cinderella dashboard at http://{host}:{port}")
    uvicorn.run(
        "api.app:app",
        host=host,
        port=port,
        reload=reload,
        workers=1 if reload else workers,
        log_level="info",
    )


if __name__ == "__main__":
    serve()
