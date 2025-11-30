"""
CMC_Observer.py - Read-only observer + optional HTTP file API for CMC.

This module is designed to be SAFE (no writes, no deletes) and to be
used by external AIs or tools to *inspect* the filesystem and environment.

It exposes a small set of helpers that CMC can call as commands:

    observer_start(state, p, port=8765)
    observer_stop(state, p)
    observer_status(state, p)

The HTTP server (when started) exposes endpoints such as:

    GET /drives
    GET /ls?path=<path>
    GET /stat?path=<path>
    GET /tree?path=<path>&depth=2
    GET /find?name=<pattern>&root=<path>&max=50

All operations are read-only. There is NO ability to modify the disk.
"""

from __future__ import annotations

import os
import json
import threading
import fnmatch
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse, parse_qs


# Global server state
_SERVER: HTTPServer | None = None
_SERVER_THREAD: threading.Thread | None = None


def _get_default_port(state: Dict[str, Any] | None = None) -> int:
    try:
        if state and isinstance(state.get("config"), dict):
            obs = state["config"].get("observer") or {}
            port = int(obs.get("port", 8765))
            if 1024 <= port <= 65535:
                return port
    except Exception:
        pass
    return 8765


def _safe_path(raw: str) -> Path:
    """
    Normalize a path string to an absolute Path without any write operations.
    """
    p = Path(raw)
    if not p.is_absolute():
        # interpret as relative to home for safety
        p = Path.home() / p
    return p.resolve()


def _list_drives() -> list[dict[str, str]]:
    """
    Very simple Windows drive detection; works on other OSes by returning ['/'].
    """
    drives = []
    if os.name == "nt":
        import string
        for letter in string.ascii_uppercase:
            root = f"{letter}:\\"
            if os.path.exists(root):
                drives.append({"path": root})
    else:
        drives.append({"path": "/"})
    return drives


def _dir_listing(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "entries": []}
    if not path.is_dir():
        return {"path": str(path), "exists": True, "is_dir": False, "entries": []}

    entries = []
    try:
        for entry in path.iterdir():
            info = {
                "name": entry.name,
                "path": str(entry),
                "is_dir": entry.is_dir(),
            }
            try:
                st = entry.stat()
                info["size"] = st.st_size
                info["mtime"] = st.st_mtime
            except Exception:
                pass
            entries.append(info)
    except Exception:
        pass
    return {"path": str(path), "exists": True, "is_dir": True, "entries": entries}


def _stat_path(path: Path) -> dict[str, Any]:
    info: dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        return info
    info["is_dir"] = path.is_dir()
    try:
        st = path.stat()
        info["size"] = st.st_size
        info["mtime"] = st.st_mtime
    except Exception:
        pass
    return info


def _tree(path: Path, depth: int = 2, max_entries: int = 200) -> dict[str, Any]:
    """
    Build a shallow tree representation, limited by depth and max_entries.
    """
    res: dict[str, Any] = {"path": str(path), "exists": path.exists(), "is_dir": path.is_dir(), "children": []}
    if not path.exists() or not path.is_dir() or depth < 1:
        return res

    queue: list[tuple[Path, int]] = [(path, 0)]
    count = 0
    children: list[dict[str, Any]] = []

    while queue and count < max_entries:
        current, d = queue.pop(0)
        try:
            for entry in current.iterdir():
                node = {
                    "path": str(entry),
                    "name": entry.name,
                    "is_dir": entry.is_dir(),
                }
                children.append(node)
                count += 1
                if count >= max_entries:
                    break
                if entry.is_dir() and d + 1 < depth:
                    queue.append((entry, d + 1))
        except Exception:
            continue

    res["children"] = children
    res["truncated"] = count >= max_entries
    return res


def _find(root: Path, pattern: str, max_results: int = 1000) -> list[dict[str, Any]]:
    """
    Best-effort name-based search. Limited by max_results.
    """
    results: list[dict[str, Any]] = []
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            # Suppress very noisy dirs
            if any(x.lower() in dirpath.lower() for x in ("\\windows", "/windows", "\\appdata", "/appdata")):
                continue
            for name in filenames + dirnames:
                if fnmatch.fnmatch(name, pattern):
                    full = Path(dirpath) / name
                    info = {
                        "path": str(full),
                        "name": name,
                        "is_dir": full.is_dir(),
                    }
                    try:
                        st = full.stat()
                        info["size"] = st.st_size
                        info["mtime"] = st.st_mtime
                    except Exception:
                        pass
                    results.append(info)
                    if len(results) >= max_results:
                        return results
    except Exception:
        pass
    return results


class ObserverHandler(BaseHTTPRequestHandler):
    server_version = "CMCObserver/1.0"

    def _send_json(self, data: Any, status: int = 200) -> None:
        payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except Exception:
            # ignore broken pipe errors
            pass

    def do_GET(self) -> None:  # type: ignore[override]
        try:
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            path = parsed.path

            # ---------------------- DRIVES ----------------------
            if path == "/drives":
                return self._send_json({"drives": _list_drives()})

            # ---------------------- LS --------------------------
            if path == "/ls":
                raw = qs.get("path", ["C:/"])[0]
                p = _safe_path(raw)
                return self._send_json(_dir_listing(p))

            # ---------------------- STAT ------------------------
            if path == "/stat":
                raw = qs.get("path", ["C:/"])[0]
                p = _safe_path(raw)
                return self._send_json(_stat_path(p))

            # ---------------------- TREE ------------------------
            if path == "/tree":
                raw = qs.get("path", ["C:/"])[0]
                depth = 2
                if "depth" in qs:
                    try:
                        depth = int(qs["depth"][0])
                    except:
                        pass
                depth = max(1, min(5, depth))
                p = _safe_path(raw)
                return self._send_json(_tree(p, depth=depth))

            # ---------------------- FIND ------------------------
            if path == "/find":
                name = qs.get("name", ["*"])[0]

                # Default root = C:/ only
                if "root" in qs:
                    roots = [qs["root"][0]]
                else:
                    roots = ["C:/"]

                max_results = 200
                if "max" in qs:
                    try:
                        max_results = max(1, min(5000, int(qs["max"][0])))
                    except:
                        pass

                all_results = []

                for r in roots:
                    try:
                        root = _safe_path(r)
                        results = _find(root, name, max_results=max_results)

                        # Apply 15-result safety cap PER ROOT
                        if len(results) > 15:
                            results = results[:15]

                    except Exception:
                        continue

                    for item in results:
                        all_results.append(item)
                        if len(all_results) >= max_results:
                            break

                    if len(all_results) >= max_results:
                        break

                # Final global limit (absolute max 15)
                if len(all_results) > 15:
                    all_results = all_results[:15]

                # SAFE JSON SEND
                try:
                    return self._send_json({
                        "roots_searched": roots,
                        "pattern": name,
                        "results": all_results,
                        "limited": True
                    })
                except Exception as e:
                    return self._send_json({
                        "error": "send_failed",
                        "detail": str(e),
                        "note": "JSON was trimmed to avoid socket abort."
                    }, status=500)

            # ---------------------- UNKNOWN ENDPOINT ------------
            return self._send_json({
                "error": "unknown_endpoint",
                "endpoints": ["/drives", "/ls", "/stat", "/tree", "/find"]
            }, status=404)

        except Exception as e:
            return self._send_json({"error": "internal_error", "detail": str(e)}, status=500)

    def log_message(self, fmt: str, *args: Any) -> None:
        return




def observer_start(state: Dict[str, Any], p, port: int | None = None) -> None:
    """
    Start the observer HTTP server in a background thread.
    Safe to call multiple times; if already running, it will just report status.
    """
    global _SERVER, _SERVER_THREAD

    if _SERVER is not None:
        p("[yellow]Observer server is already running.[/yellow]")
        return

    if port is None:
        port = _get_default_port(state)

    try:
        server = HTTPServer(("127.0.0.1", port), ObserverHandler)
    except OSError as e:
        p(f"[red]Failed to start observer server on port {port}:[/red] {e}")
        return

    def _run():
        try:
            server.serve_forever()
        except Exception:
            pass

    thread = threading.Thread(target=_run, name="CMCObserverServer", daemon=True)
    thread.start()

    _SERVER = server
    _SERVER_THREAD = thread

    obs = state.setdefault("observer", {})
    obs["running"] = True
    obs["port"] = port

    


def observer_stop(state: Dict[str, Any], p) -> None:
    """
    Stop the observer HTTP server, if running.
    """
    global _SERVER, _SERVER_THREAD

    if _SERVER is None:
        p("[yellow]Observer server is not running.[/yellow]")
        return

    try:
        _SERVER.shutdown()
    except Exception:
        pass

    _SERVER = None
    _SERVER_THREAD = None

    obs = state.setdefault("observer", {})
    obs["running"] = False

    p("[green]Observer server stopped.[/green]")


def observer_status(state: Dict[str, Any], p) -> None:
    """
    Print observer server status.
    """
    if _SERVER is not None:
        port = getattr(_SERVER.server_address, "__getitem__", lambda x: None)(1)
        if not port:
            port = state.get("observer", {}).get("port", _get_default_port(state))
        p(f"[green]Observer server is running[/green] on http://127.0.0.1:{port}")
    else:
        p("[yellow]Observer server is not running.[/yellow]")
