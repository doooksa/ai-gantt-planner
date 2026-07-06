"""Process-wide singletons and configuration (settings, Storage, LLM client).

The MCP tools, the REST routes and the agent all share ONE Storage instance so
a mutation made through any path is visible everywhere. Tests swap it for an
in-memory store via `set_storage`.
"""

from __future__ import annotations

import os
from datetime import date

from .storage.db import Storage

# --- settings (env) -------------------------------------------------------


class Settings:
    def __init__(self) -> None:
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
        self.llm_model = os.getenv("LLM_MODEL", "anthropic/claude-sonnet-4.5")
        self.frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
        # DATABASE_URL like "sqlite:///./gantt.db" -> path "./gantt.db".
        url = os.getenv("DATABASE_URL", "sqlite:///./gantt.db")
        self.db_path = url.split("///", 1)[1] if "///" in url else "gantt.db"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


# --- storage --------------------------------------------------------------

_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        _storage = Storage(get_settings().db_path)
        _storage.ensure_seeded()
    return _storage


def set_storage(storage: Storage) -> None:
    """Override the shared storage (used by tests)."""
    global _storage
    _storage = storage


# --- scheduling reference date -------------------------------------------


def get_project_start() -> date:
    """Project start used for all date derivation. Today, per spec."""
    return date.today()


# --- LLM client -----------------------------------------------------------


def make_llm_client():
    """Create an AsyncOpenAI client pointed at OpenRouter.

    Raises a clear error if the key is missing so the failure is obvious rather
    than a confusing auth error deep in a request.
    """
    from openai import AsyncOpenAI

    settings = get_settings()
    if not settings.openrouter_api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY не задан. Скопируйте .env.example в .env и "
            "укажите ключ OpenRouter."
        )
    return AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.openrouter_api_key,
    )
