"""
CMC_Config.py - Persistent configuration for Computer Main Centre (CMC)

This module provides a small nested-JSON config system, with helpers:

- load_config(base_dir: Path | None = None) -> dict
- save_config(config: dict, base_dir: Path | None = None) -> None
- get_config_value(config: dict, key: str, default=None)
- set_config_value(config: dict, key: str, value) -> dict
- apply_config_to_state(config: dict, state: dict) -> None

Keys support dotted paths, e.g.:

    "batch"
    "observer.auto"
    "space.default_depth"
    "space.auto_ai"
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


DEFAULT_CONFIG: Dict[str, Any] = {
    "batch": False,
    "dry_run": False,
    "ssl_verify": True,
    "observer": {
        "auto": False,
        "port": 8765,
    },
    "space": {
        "default_depth": 2,
        "auto_ai": False,
        "auto_report": False,
    },
    "ai": {
        "verbose": False,
    },
}


def _get_config_path(base_dir: Path | None = None) -> Path:
    if base_dir is None:
        base_dir = Path(__file__).parent
    return base_dir / "CMC_Config.json"


def _deep_update(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in updates.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_update(out[k], v)
        else:
            out[k] = v
    return out


def load_config(base_dir: Path | None = None) -> Dict[str, Any]:
    """
    Load config from JSON, merge with DEFAULT_CONFIG, and return the dict.
    Never raises if the file is missing or invalid; falls back to defaults.
    """
    cfg_path = _get_config_path(base_dir)
    cfg: Dict[str, Any] = {}
    if cfg_path.exists():
        try:
            text = cfg_path.read_text(encoding="utf-8")
            data = json.loads(text)
            if isinstance(data, dict):
                cfg = data
        except Exception:
            # Ignore parse errors; use empty + defaults
            cfg = {}
    merged = _deep_update(DEFAULT_CONFIG, cfg)
    return merged


def save_config(config: Dict[str, Any], base_dir: Path | None = None) -> None:
    """
    Save config dict to disk as JSON (pretty-printed).
    """
    cfg_path = _get_config_path(base_dir)
    try:
        cfg_path.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")
    except Exception:
        # Best-effort; ignore write failures
        pass


def get_config_value(config: Dict[str, Any], key: str, default: Any = None) -> Any:
    """
    Get a value from a possibly-nested config using dotted keys.
    Example: get_config_value(cfg, "space.default_depth", 2)
    """
    if not key:
        return default
    parts = key.split(".")
    cur: Any = config
    for part in parts:
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur


def set_config_value(config: Dict[str, Any], key: str, value: Any) -> Dict[str, Any]:
    """
    Set a value in a possibly-nested config using dotted keys.
    Returns the modified config dict.
    """
    if not key:
        return config
    parts = key.split(".")
    cur = config
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value
    return config


def _to_bool(s: str) -> bool | None:
    s = s.strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off"):
        return False
    return None


def parse_value(raw: str) -> Any:
    """
    Parse a string value into bool/int/float/str where sensible.
    """
    b = _to_bool(raw)
    if b is not None:
        return b
    # Try int
    try:
        i = int(raw)
        return i
    except Exception:
        pass
    # Try float
    try:
        f = float(raw)
        return f
    except Exception:
        pass
    return raw


def apply_config_to_state(config: Dict[str, Any], state: Dict[str, Any]) -> None:
    """
    Apply top-level config flags to the shared STATE dict.
    This lets CMC start with batch/dry_run/ssl_verify defaults.
    """
    state["batch"] = bool(config.get("batch", state.get("batch", False)))
    state["dry_run"] = bool(config.get("dry_run", state.get("dry_run", False)))
    state["ssl_verify"] = bool(config.get("ssl_verify", state.get("ssl_verify", True)))
    # Observer + space config are consumed by their respective modules at runtime.
