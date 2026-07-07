"""Process-wide singletons and configuration (settings, Storage, LLM client).

The MCP tools, the REST routes and the agent all share ONE Storage instance so
a mutation made through any path is visible everywhere. Tests swap it for an
in-memory store via `set_storage`.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from .storage.db import Storage

# --- .env loading (zero-dependency) --------------------------------------

# Backend root: .../apps/backend (one level above the `app` package).
_BACKEND_ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path | None = None) -> None:
    """Populate os.environ from a .env file. Does NOT override already-set vars
    (real environment wins over the file). No external dependency."""
    env_path = path or (_BACKEND_ROOT / ".env")
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


# --- settings (env) -------------------------------------------------------


class Settings:
    def __init__(self) -> None:
        # --- LLM provider profile (OpenAI-compatible) --------------------
        # Configurable so we can point the same OpenAI SDK at any compatible
        # endpoint. Defaults = OpenRouter. For Google AI Studio set:
        #   LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
        #   LLM_API_KEY_ENV=GOOGLE_API_KEY
        #   LLM_MODEL=gemini-2.5-flash
        self.llm_base_url = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
        # Name of the env var that holds the API key (indirection so the key
        # variable can differ per provider, e.g. OPENROUTER_API_KEY vs GOOGLE_API_KEY).
        self.llm_api_key_env = os.getenv("LLM_API_KEY_ENV", "OPENROUTER_API_KEY")
        self.llm_api_key = os.getenv(self.llm_api_key_env, "")
        self.llm_model = os.getenv("LLM_MODEL", "anthropic/claude-haiku-4.5")
        # FRONTEND_ORIGIN may be a single origin or a comma-separated list
        # (prod URL + Vercel preview URLs). Kept as a raw string for back-compat;
        # `frontend_origins` is the parsed list used for CORS.
        self.frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
        self.frontend_origins = [
            o.strip() for o in self.frontend_origin.split(",") if o.strip()
        ]
        # DATABASE_URL like "sqlite:///./gantt.db" -> path "./gantt.db".
        url = os.getenv("DATABASE_URL", "sqlite:///./gantt.db")
        self.db_path = url.split("///", 1)[1] if "///" in url else "gantt.db"
        # Deployed commit (Render injects RENDER_GIT_COMMIT), surfaced by
        # /api/health so we can confirm which build is actually live.
        self.commit = os.getenv("RENDER_GIT_COMMIT", "dev")[:7]


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        load_dotenv()
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
    """Create an AsyncOpenAI client pointed at the configured provider.

    Raises a clear error if the key is missing so the failure is obvious rather
    than a confusing auth error deep in a request.
    """
    from openai import AsyncOpenAI

    settings = get_settings()
    if not settings.llm_api_key:
        raise RuntimeError(
            f"{settings.llm_api_key_env} не задан. Скопируйте .env.example в .env "
            f"и укажите ключ LLM-провайдера."
        )
    return AsyncOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
    )
