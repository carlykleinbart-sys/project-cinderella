"""Serve the HTML dashboard."""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["dashboard"])
_TEMPLATE = (Path(__file__).parent.parent / "templates" / "dashboard.html").read_text()


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard():
    return HTMLResponse(content=_TEMPLATE)
