"""
assistant_core.py — Embedded AI assistant integration for Computer Main Centre (CMC).

This variant is preconfigured to talk to a LOCAL Ollama server
running on http://localhost:11434.

It expects:
  - Ollama installed (https://ollama.com/)
  - At least one chat-capable model pulled, e.g.:  `ollama pull llama3.2`

CMC remains fully usable without this file; the `ai` command will
simply report that the assistant is unavailable if import fails.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Manual loading
# ---------------------------------------------------------------------------

_MANUAL_CACHE: Optional[str] = None


def _default_manual_path() -> Path:
    """
    Default location of CMC_AI_Manual.md:

    1. If env var CMC_AI_MANUAL is set -> use that path.
    2. Else, assume it lives next to this assistant_core.py.
    """
    env = os.getenv("CMC_AI_MANUAL")
    if env:
        return Path(env).expanduser()
        
    here = Path(__file__).resolve().parent
    # Prefer MINI manual if present
    mini = here / "CMC_AI_Manual_MINI.md"
    if mini.exists():
        return mini
    return here / "CMC_AI_Manual.md"



def load_cmc_manual(path: Optional[Path | str] = None) -> str:
    """
    Load the AI manual from disk (cached in memory).

    If it cannot be loaded, a short placeholder is returned.
    """
    global _MANUAL_CACHE
    if _MANUAL_CACHE is not None:
        return _MANUAL_CACHE

    manual_path = Path(path) if path is not None else _default_manual_path()
    try:
        _MANUAL_CACHE = manual_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        _MANUAL_CACHE = (
            "# CMC AI Manual missing\n"
            "The file CMC_AI_Manual.md could not be found. "
            "Create or place it next to assistant_core.py or set CMC_AI_MANUAL.\n"
        )
    return _MANUAL_CACHE


# ---------------------------------------------------------------------------
# Context building helpers
# ---------------------------------------------------------------------------


def build_context_blob(cwd: str, state: Dict[str, Any], macros: Dict[str, str]) -> str:
    """
    Turn the current CMC state into a compact JSON-like context string.

    Only includes safe, high-level info:
      - current working directory
      - batch / dry-run / ssl flags
      - list of macro names (no bodies)
    """
    safe_state = {
        "cwd": cwd,
        "state": {
            "batch": bool(state.get("batch", False)),
            "dry_run": bool(state.get("dry_run", False)),
            "ssl_verify": bool(state.get("ssl_verify", True)),
        },
        "macros": sorted(list(macros.keys())),
    }
    return json.dumps(safe_state, indent=2, ensure_ascii=False)


def build_system_prompt(cwd: str, state: Dict[str, Any], macros: Dict[str, str]) -> str:
    """
    Build a single large system prompt string that includes:

      - The full AI-only CMC manual
      - A short, explicit set of behavioral rules
      - The *current* CMC context (cwd, flags, macros)
    """
    manual = load_cmc_manual()
    ctx = build_context_blob(cwd, state, macros)

    prefix = (
        "You are the embedded AI assistant for Computer Main Centre (CMC).\n"
        "Your job is to help the user by generating **valid CMC commands** "
        "and clear explanations when asked.\n\n"
        "Rules you MUST follow (summary):\n"
        "  - Obey the CMC_AI_Manual.md content exactly.\n"
        "  - Use single quotes for all file paths.\n"
        "  - Use semicolons to chain multiple commands; no trailing semicolons.\n"
        "  - Never invent new commands or future features.\n"
        "  - Never perform destructive actions (delete, gitclean, etc.) "
        "    unless the user clearly and explicitly requests them.\n"
        "  - Prefer explanations in plain text, and when commands are requested, "
        "    output them in fenced code blocks.\n"
        "  - When unsure, ask a brief clarifying question instead of guessing.\n\n"
        "Current CMC context (JSON):\n"
        f"{ctx}\n\n"
        "Below is the full CMC AI manual you must treat as ground truth:\n"
        "----- BEGIN CMC_AI_Manual.md -----\n"
    )

    suffix = "\n----- END CMC_AI_Manual.md -----\n"
    return prefix + manual + suffix


# ---------------------------------------------------------------------------
# Ollama backend integration
# ---------------------------------------------------------------------------

_OLLAMA_MODEL = os.getenv("CMC_AI_MODEL", "qwen2.5:7b-instruct")
_OLLAMA_URL = os.getenv("CMC_AI_OLLAMA_URL", "http://localhost:11434/api/chat")


def _call_ai_backend(messages: List[Dict[str, str]]) -> str:
    """
    Call a local Ollama server with a ChatGPT-style messages list.

    Requirements:
      - Ollama installed
      - `ollama serve` running (usually started automatically)
      - A chat-capable model pulled (default: llama3.2)

    Environment overrides:
      - CMC_AI_MODEL       -> model name (default: llama3.2)
      - CMC_AI_OLLAMA_URL -> base URL (default: http://localhost:11434/api/chat)
    """
    try:
        import requests  # type: ignore
    except Exception as exc:  # pragma: no cover - very environment-specific
        raise RuntimeError(
            "The 'requests' library is required for the CMC AI assistant but is not installed.\n"
            "Install it in your Python environment, e.g.:  pip install requests"
        ) from exc

    payload = {
        "model": _OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.2,
        },
    }

    try:
        resp = requests.post(_OLLAMA_URL, json=payload, timeout=120)
    except Exception as exc:
        raise RuntimeError(
            f"Could not reach Ollama at {_OLLAMA_URL}. Is Ollama installed and running?\n"
            "Try:  ollama pull llama3.2  and then start the Ollama app."
        ) from exc

    if resp.status_code != 200:
        raise RuntimeError(
            f"Ollama returned HTTP {resp.status_code}: {resp.text[:300]}"
        )

    try:
        data = resp.json()
    except Exception as exc:
        raise RuntimeError(f"Failed to decode Ollama JSON response: {resp.text[:300]}") from exc

    # Ollama chat API usually returns: {"message": {"role": "assistant", "content": "..."}, ...}
    content = None
    if isinstance(data, dict):
        msg = data.get("message") or {}
        content = msg.get("content")
        if not content and "choices" in data:
            # Fallback if some OpenAI-style bridge is used
            choices = data.get("choices") or []
            if choices:
                content = (choices[0].get("message") or {}).get("content")

    if not content:
        raise RuntimeError(f"Ollama reply did not contain content: {data!r}")

    return str(content).strip()


# ---------------------------------------------------------------------------
# Public entry point used by Computer_Main_Centre.py
# ---------------------------------------------------------------------------


def run_ai_assistant(
    user_query: str,
    cwd: str,
    state: Dict[str, Any],
    macros: Dict[str, str],
) -> str:
    """
    Main entry point for CMC.

    Parameters
    ----------
    user_query:
        The raw text after the `ai` command, e.g.:
            ai how do I back up my project?
            ai "create a macro to zip and commit"

    cwd:
        Current working directory as string.

    state:
        The global STATE dict from CMC. Only a subset is used (batch, dry_run, ssl_verify).

    macros:
        The MACROS dict (name -> command string). Only keys are used.

    Returns
    -------
    reply_text:
        A string containing either:
        - explanation only (for how-to questions)
        - or a mix of explanation + fenced command blocks
          (for automation / macro design questions)
    """
    system_prompt = build_system_prompt(cwd, state, macros)

    messages: List[Dict[str, str]] = [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": user_query.strip(),
        },
    ]

    reply = _call_ai_backend(messages)
    return reply.strip()


if __name__ == "__main__":
    # Small local test-loop for the assistant_core + Ollama wiring.
    import textwrap

    cwd = os.getcwd()
    state = {"batch": False, "dry_run": False, "ssl_verify": True}
    macros: Dict[str, str] = {}

    print("assistant_core (Ollama) demo shell.")
    print("Requires Ollama + a model (default: llama3.2).")
    print("Ctrl+C to exit.\n")

    try:
        while True:
            q = input("ai> ").strip()
            if not q:
                continue
            try:
                ans = run_ai_assistant(q, cwd, state, macros)
            except Exception as e:
                print(f"[assistant_core] Error: {e}")
            else:
                print("\n--- AI reply ---")
                print(textwrap.indent(ans, "  "))
                print("----------------\n")
    except KeyboardInterrupt:
        print("\nExiting assistant_core demo.")
