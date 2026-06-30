"""Dashboard route for the operations UI.

Per D-01: Dashboard served at /dashboard, separate from /admin/* JSON API.
Per D-02: Client-side fetch -- HTML shell rendered by Jinja2, JS fetches /admin/nodes.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

dashboard_router = APIRouter(tags=["dashboard"])


@dashboard_router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    """Render the operations dashboard HTML shell."""
    return templates.TemplateResponse(request=request, name="dashboard.html")
