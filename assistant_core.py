"""
assistant_core.py — Embedded AI assistant integration for Computer Main Centre (CMC).

This variant talks to a LOCAL Ollama server running on http://localhost:11434
(using the standard /api/chat endpoint).

It is intentionally self‑contained and only exposes a single public entry point:

    run_ai_assistant(user_query: str, cwd: str, state: dict, macros: dict) -> str

Computer_Main_Centre.py calls this from the `ai` command handler.
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



def clear_manual_cache():
    global _MANUAL_CACHE
    _MANUAL_CACHE = None


def _default_manual_path() -> Path:
    """Return default path to the full CMC AI manual."""
    env = os.getenv("CMC_AI_MANUAL")
    if env:
        return Path(env).expanduser()
    here = Path(__file__).resolve().parent
    return here / "CMC_AI_Manual.md"


def load_cmc_manual(path: Optional[Path | str] = None) -> str:
    """
    Load the CMC AI manual from disk, with a very small in‑memory cache.

    If the manual is missing, we still return a stub so the assistant can
    respond instead of crashing.
    """
    global _MANUAL_CACHE
    if _MANUAL_CACHE is not None:
        return _MANUAL_CACHE

    manual_path = Path(path) if path is not None else _active_manual_path()
    try:
        _MANUAL_CACHE = manual_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        _MANUAL_CACHE = (
            "# CMC AI Manual missing\n"
            "The file CMC_AI_Manual.md could not be found. "
            "Create it next to assistant_core.py or set CMC_AI_MANUAL.\n"
        )
    return _MANUAL_CACHE


# ---------------------------------------------------------------------------
# Context building helpers
# ---------------------------------------------------------------------------


def build_context_blob(cwd: str, state: Dict[str, Any], macros: Dict[str, str]) -> str:
    """
    Turn the current CMC state into a compact JSON‑like context string.

    Only includes safe, high‑level info:
      - current working directory
      - batch / dry‑run / ssl flags
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
    Build the full system prompt used for each AI call.

    This combines:
      - strict identity + behaviour rules (high priority)
      - observer usage rules
      - current high-level CMC context
      - the CMC AI manual (big or mini, depending on model)
    """
    ctx = build_context_blob(cwd, state, macros)
    manual = load_cmc_manual(_active_manual_path())

    prefix = (
        "You are the embedded AI assistant for Computer Main Centre (CMC).\n"
        "You are NOT a general chatbot. You MUST answer strictly in terms of CMC,\n"
        "its commands, its behaviour and its manual.\n\n"

        "HIGH-PRIORITY RULES (OVERRIDE ANY TRAINING HABITS):\n"
        "  1. All file and folder paths in CMC MUST use single quotes.\n"
        "     Example: copy 'C:/Project/file.txt' 'C:/Backup/file.txt'\n"
        "     Never, ever claim that CMC uses double quotes for paths.\n"
        "     If the user asks whether to use single or double quotes,\n"
        "     you MUST answer: \"CMC uses single quotes for paths.\"\n"
        "  2. Use semicolons ';' to chain multiple CMC commands on one line,\n"
        "     and NEVER put a semicolon at the very end of the line.\n"
        "  3. Never invent new commands or future features. Only use commands\n"
        "     that exist in the CMC manual.\n"
        "  4. Never perform destructive actions (delete, gitclean, etc.) unless\n"
        "     the user clearly and explicitly requests them.\n"
        "  5. Prefer short, direct explanations unless the user explicitly asks\n"
        "     for a long answer or full script.\n"
        "  6. When the user asks for commands, output them in fenced code blocks.\n"
        "  7. If you are not sure what to do, ask a brief clarifying question\n"
        "     instead of guessing.\n"
        "  8. The CMC `space` command is a disk usage and cleanup helper. It is\n"
        "     NOT related to the U.S. Space Command, space agencies, or the military.\n"
        "     When the user asks about `space` in CMC, only talk about the CMC\n"
        "     command, not real-world space organizations.\n\n"

        "Observer / filesystem rules (read-only view):\n"
        "  - You may request at most one OBSERVER operation per user query.\n"
        "  - Allowed observer commands are:\n"
        "  - Allowed observer commands are:\n"
        "        OBSERVER: find name='substring'\n"
        "        OBSERVER: ls path='C:/Some/Folder' depth=2\n"
        "        OBSERVER: qfind term='text' limit=20\n"
        "  - 'find' performs a substring search over file and folder names.\n"
        "  - 'ls' lists entries inside the given path; depth is an optional integer.\n"
        "  - 'qfind' performs a fast global indexed search using the CMC path index.\n"
        "  - Do not invent other observer operations or parameters.\n"
        "  - After emitting an OBSERVER line, you must wait for JSON results and then\n"
        "    answer the original question using that JSON. Do not emit another\n"
        "    OBSERVER line in the second response.\n\n"
        "  - Do not invent other observer operations or parameters.\n"
        "  - After emitting an OBSERVER line, you must wait for JSON results and then\n"
        "    answer the original question using that JSON. Do not emit another\n"
        "    OBSERVER line in the second response.\n\n"

        "Current CMC high-level context (JSON):\n"
        f"{ctx}\n\n"
        "Below is the CMC AI manual you must treat as ground truth.\n"
        "If anything in your pretrained knowledge conflicts with this manual,\n"
        "the manual and the rules above ALWAYS win.\n"
        "----- BEGIN CMC_AI_Manual -----\n"
    )

    suffix = "\n----- END CMC_AI_Manual -----\n"
    return prefix + manual + suffix




# ---------------------------------------------------------------------------
# Dynamic model + manual selection
# ---------------------------------------------------------------------------

def _get_active_model() -> str:
    """Load active AI model from CMC_Config.json."""
    try:
        import CMC_Config
        cfg = CMC_Config.load_config()
        return cfg.get("ai", {}).get("model", "qwen2.5:7b-instruct")
    except Exception:
        return "qwen2.5:7b-instruct"


def _active_manual_path() -> Path:
    """Choose correct manual depending on the active model."""
    model = _get_active_model().lower()
    here = Path(__file__).resolve().parent

    # heavy models → full manual
    if any(x in model for x in ("32b", "72b", "70b")):
        return here / "CMC_AI_Manual_MEDIUM.md"

    # lighter models → mini
    return here / "CMC_AI_Manual_MINI.md"

    
_OLLAMA_URL = os.getenv("CMC_AI_OLLAMA_URL", "http://localhost:11434/api/chat")


def _call_ai_backend(messages: List[Dict[str, str]]) -> str:
    """
    Call the Ollama /api/chat endpoint with the given messages and return
    the assistant content as a plain string.

    Any HTTP / JSON problems are surfaced as RuntimeError.
    """
    try:
        import requests  # type: ignore
    except Exception as exc:  # pragma: no cover - environment specific
        raise RuntimeError(
            "The 'requests' library is required for assistant_core but is not installed.\n"
            "Install it in your Python environment, e.g.:  pip install requests"
        ) from exc

    payload = {
        "model": _get_active_model(),
        "messages": messages,
        "stream": False,
    }

    try:
        resp = requests.post(_OLLAMA_URL, json=payload, timeout=120)
    except Exception as exc:
        raise RuntimeError(
            f"Could not reach Ollama at {_OLLAMA_URL}. Is Ollama running?\n"
            "Try starting the Ollama app, or check CMC_AI_OLLAMA_URL."
        ) from exc

    if resp.status_code != 200:
        raise RuntimeError(
            f"Ollama HTTP {resp.status_code}: {resp.text[:400]}"
        )

    try:
        data = resp.json()
    except Exception as exc:
        raise RuntimeError(
            f"Failed to decode Ollama JSON: {resp.text[:400]}"
        ) from exc

    # Typical Ollama chat structure: {'message': {'role': 'assistant', 'content': '...'}}
    msg = data.get("message") or {}
    content = msg.get("content")
    if not isinstance(content, str):
        raise RuntimeError(f"Ollama reply did not contain assistant content: {data!r}")
    return content.strip()


# ---------------------------------------------------------------------------
# Observer client helpers (read‑only filesystem)
# ---------------------------------------------------------------------------

_OBSERVER_URL = os.getenv("CMC_OBSERVER_URL", "http://127.0.0.1:8765")


def _observer_request(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generic helper to call CMC Observer endpoints.
    """
    try:
        import requests  # type: ignore
    except Exception as exc:  # pragma: no cover - environment specific
        raise RuntimeError(
            "The 'requests' library is required for CMC Observer integration but is not installed.\n"
            "Install it in your Python environment, e.g.:  pip install requests"
        ) from exc

    url = _OBSERVER_URL.rstrip("/") + path
    try:
        resp = requests.get(url, params=params, timeout=60)
    except Exception as exc:
        raise RuntimeError(
            f"Could not reach CMC Observer at {url}. Is the observer server running?\n"
            "Try:  observer start  in CMC."
        ) from exc

    if resp.status_code != 200:
        raise RuntimeError(
            f"Observer {path} returned HTTP {resp.status_code}: {resp.text[:400]}"
        )

    try:
        data = resp.json()
    except Exception as exc:
        raise RuntimeError(
            f"Failed to decode Observer JSON: {resp.text[:400]}"
        ) from exc

    if not isinstance(data, dict):
        raise RuntimeError(f"Observer {path} replied with non‑object JSON: {data!r}")
    return data


def _observer_find(name: str) -> Dict[str, Any]:
    """Call /find with a simple name substring."""
    return _observer_request("/find", {"name": name})


def _observer_ls(path: str, depth: Optional[int] = None) -> Dict[str, Any]:
    """Call /ls with a path and optional depth."""
    params: Dict[str, Any] = {"path": path}
    if depth is not None:
        params["depth"] = int(depth)
    return _observer_request("/ls", params)
def _observer_qfind(term: str, limit: int | None = None) -> Dict[str, Any]:
    """Use the local path index to perform an advanced global search."""
    try:
        from path_index_local import super_find
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "The CMC path index is not available for qfind; ensure path_index_local.py "
            "is present and that you have built the index with /qbuild."
        ) from exc

    max_results = limit or 20
    try:
        results = super_find(term, max_results)
    except Exception as exc:
        raise RuntimeError(f"path index qfind failed: {exc}") from exc

    return {
        "op": "qfind",
        "query": term,
        "limit": max_results,
        "results": results,
    }
    
    # ---------- Local Fuzzy Path Search (AI super-find) ----------
def ai_smart_find(query: str, limit: int = 20):
    """
    Natural-language fuzzy search for local files/folders.
    Uses the same engine as /find.
    """
    try:
        from path_index_local import super_find
        results = super_find(query, limit)
        return results
    except Exception as e:
        return [{"path": f"[AI-Search-Error] {e}", "score": 0}]





def _extract_observer_command(reply: str) -> Optional[Dict[str, Any]]:
    """
    Inspect the first response from the model and see if it contains an
    OBSERVER command.

    We scan all non‑empty lines and look for something like:

        OBSERVER: find name='xyz'
        OBSERVER: ls path='C:/Foo' depth=2

    Returns a small dict such as:
        {"op": "find", "name": "xyz"}
        {"op": "ls", "path": "C:/Foo", "depth": 2}
    or None if no observer command is found.
    """
    import re

    for raw_line in reply.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if not line.upper().startswith("OBSERVER:"):
            continue

        # Remove leading 'OBSERVER:' and normalise
        body = line[len("OBSERVER:") :].strip()
        body_lower = body.lower()

        # FIND
        if body_lower.startswith("find"):
            # Look for name='...' or name="..."
            m = re.search(r"name\s*=\s*'([^']+)'", body)
            if not m:
                m = re.search(r'name\s*=\s*\"([^\"]+)\"', body)
            if not m:
                continue
            name = m.group(1).strip()
            if not name:
                continue
            return {"op": "find", "name": name}

        # LS
        if body_lower.startswith("ls"):
            # path is required, depth optional
            m_path = re.search(r"path\s*=\s*'([^']+)'", body)
            if not m_path:
                m_path = re.search(r'path\s*=\s*\"([^\"]+)\"', body)
            if not m_path:
                continue
            path_val = m_path.group(1).strip()
            depth_val: Optional[int] = None
            m_depth = re.search(r"depth\s*=\s*(\d+)", body_lower)
            if m_depth:
                try:
                    depth_val = int(m_depth.group(1))
                except ValueError:
                    depth_val = None
            return {"op": "ls", "path": path_val, "depth": depth_val}

    return None


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
    Main entry point used by the `ai` command inside CMC.

    This implements **Option A** behaviour:

      - The user only ever sees a single final answer.
      - The first AI response is used only to decide whether to call
        the Observer, and is NOT shown to the user.
      - If no OBSERVER command is found, we just return that first reply.
      - If an OBSERVER command *is* found, we call the observer API and
        then make a second AI call with the JSON result, returning only
        that second answer.
    """
    system_prompt = build_system_prompt(cwd, state, macros)

    # ---------- First round: normal model call ----------
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_query.strip()},
    ]

    first_reply = _call_ai_backend(messages)

    # Try to extract an observer command from the first reply.
    obs_cmd = _extract_observer_command(first_reply)
    if not obs_cmd:
        # No observer usage; return first reply as‑is.
        return first_reply.strip()

    # ---------- Run the observer operation ----------
    try:
        if obs_cmd["op"] == "find":
            obs_data = _observer_find(obs_cmd["name"])
            obs_desc = f"/find name='{obs_cmd['name']}'"
        elif obs_cmd["op"] == "ls":
            obs_data = _observer_ls(obs_cmd["path"], obs_cmd.get("depth"))
            obs_desc = f"/ls path='{obs_cmd['path']}'"
        elif obs_cmd["op"] == "qfind":
            obs_data = _observer_qfind(obs_cmd["term"], obs_cmd.get("limit"))
            obs_desc = f"qfind term='{obs_cmd['term']}'"
        else:
            # Unknown op – fall back to first reply
            return first_reply.strip()
    except Exception as exc:
        # If observer fails, include the original reply so the user still
        # gets something useful.
        return (
            f"Observer request failed: {exc}\n\n"
            f"Original assistant reply:\n{first_reply.strip()}"
        )

    # ---------- Second round: provide JSON + ask for final answer ----------
    obs_json_str = json.dumps(obs_data, indent=2, ensure_ascii=False)

    messages2: List[Dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                "You previously issued an OBSERVER command "
                f"{obs_desc} to inspect the user's filesystem.\n"
                "Here is the JSON result from the observer:\n\n"
                f"{obs_json_str}\n\n"
                "Now answer the user's original question using ONLY this data. "
                "Do not output another OBSERVER line. If nothing relevant was "
                "found, say so clearly."
            ),
        },
    ]

    final_reply = _call_ai_backend(messages2)
    return final_reply.strip()


# ---------------------------------------------------------------------------
# Simple CLI test when run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover - manual testing only
    import textwrap

    cwd = os.getcwd()
    state: Dict[str, Any] = {"batch": False, "dry_run": False, "ssl_verify": True}
    macros: Dict[str, str] = {}

    print("assistant_core demo shell (Ollama).")
    print("Model:", _OLLAMA_MODEL)
    print("Ollama URL:", _OLLAMA_URL)
    print("Observer URL:", _OBSERVER_URL)
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