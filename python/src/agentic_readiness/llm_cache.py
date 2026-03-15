"""Dev cache for LLM responses. Keyed by (provider, prompt) hash."""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Optional


def _cache_path() -> Path:
    root = Path(__file__).resolve().parents[3]  # project root
    cache_dir = root / ".cache"
    cache_dir.mkdir(exist_ok=True)
    return cache_dir / "llm_responses.json"


_lock = threading.Lock()
_memory: dict[str, str] = {}


def _key(provider: str, prompt: str) -> str:
    h = hashlib.sha256(f"{provider}:{prompt}".encode("utf-8")).hexdigest()
    return f"{provider}_{h[:16]}"


def get(provider: str, prompt: str) -> Optional[str]:
    """Return cached response or None."""
    k = _key(provider, prompt)
    with _lock:
        if k in _memory:
            return _memory[k]
        path = _cache_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if k in data:
                    return data[k]
            except Exception:
                pass
    return None


def set_(provider: str, prompt: str, response: str) -> None:
    """Store response in cache (memory + file)."""
    k = _key(provider, prompt)
    with _lock:
        _memory[k] = response
        path = _cache_path()
        data = {}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        data[k] = response
        try:
            path.write_text(json.dumps(data, indent=0), encoding="utf-8")
        except Exception:
            pass
