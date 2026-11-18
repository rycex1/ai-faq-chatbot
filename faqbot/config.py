"""Settings from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    business_name: str = "Sunrise Bakery"
    docs_dir: Path = PROJECT_ROOT / "sample_docs"
    model: str = "claude-haiku-5-5"
    max_tokens: int = 4096
    top_k: int = 4
    chunk_chars: int = 900
    api_key_set: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        docs = Path(os.getenv("FAQBOT_DOCS_DIR") or cls.docs_dir)
        if not docs.is_absolute():
            docs = (Path.cwd() / docs).resolve()
        return cls(
            business_name=os.getenv("FAQBOT_BUSINESS_NAME") or cls.business_name,
            docs_dir=docs,
            model=os.getenv("FAQBOT_MODEL") or cls.model,
            max_tokens=int(os.getenv("FAQBOT_MAX_TOKENS") or cls.max_tokens),
            top_k=int(os.getenv("FAQBOT_TOP_K") or cls.top_k),
            chunk_chars=int(os.getenv("FAQBOT_CHUNK_CHARS") or cls.chunk_chars),
            api_key_set=bool(os.getenv("ANTHROPIC_API_KEY", "").strip()),
        )
