"""Small web chat: FastAPI backend + a single static HTML page.

    python -m faqbot.web                 # http://127.0.0.1:8000
    python -m faqbot.web --dry-run       # no API key needed; shows retrieval + prompt
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .bot import AnswerError, FAQBot
from .config import Settings

STATIC = Path(__file__).parent / "static"
log = logging.getLogger("faqbot.web")


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    history: list[Turn] = Field(default_factory=list, max_length=20)


def create_app(settings: Settings | None = None, dry_run: bool | None = None, client=None) -> FastAPI:
    settings = settings or Settings.from_env()
    if dry_run is None:
        dry_run = os.getenv("FAQBOT_DRY_RUN", "").lower() in ("1", "true", "yes") or not settings.api_key_set
    bot = FAQBot(settings, client=client)
    if dry_run:
        log.warning("Running in dry-run mode: no API calls, responses show retrieval and the prompt.")

    app = FastAPI(title=f"{settings.business_name} FAQ bot", docs_url=None, redoc_url=None)

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/api/info")
    def info() -> dict:
        return {"business": settings.business_name, "mode": "dry-run" if dry_run else "live", "chunks": len(bot.chunks)}

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/api/chat")
    def chat(req: ChatRequest) -> dict:
        history = [t.model_dump() for t in req.history]
        try:
            ans = bot.answer(req.message, history=history, dry_run=dry_run)
        except AnswerError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        body = {"answer": ans.text, "sources": ans.sources(), "mode": "dry-run" if dry_run else "live"}
        if dry_run:
            body["prompt"] = {"model": settings.model, "system": ans.system, "messages": ans.messages}
        return body

    return app


def main() -> None:
    import uvicorn

    p = argparse.ArgumentParser(prog="faqbot.web", description="Run the FAQ web chat.")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--dry-run", action="store_true", help="never call the API (automatic when no key is set)")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    uvicorn.run(create_app(dry_run=True if args.dry_run else None), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
