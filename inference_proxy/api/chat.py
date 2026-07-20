"""Chat page route for the chatbot playground UI.

Serves the chat HTML shell at /chat. Client-side JS handles
model selection, message sending, and streaming responses.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

chat_router = APIRouter(tags=["chat"])


@chat_router.get("/chat", response_class=HTMLResponse)
async def chat(request: Request) -> HTMLResponse:
    """Render the chat playground HTML shell."""
    return templates.TemplateResponse(request=request, name="chat.html")
