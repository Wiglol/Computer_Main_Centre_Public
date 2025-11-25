"""
CMC_Space.py - Advanced disk usage + AI cleanup helper for Computer Main Centre (CMC).

This module is intentionally standalone. It exposes a single entrypoint:

    op_space(command: str, cwd: Path, state: dict, macros: dict, p: callable, rich: bool)

It parses the `space` command, scans disk usage for the selected path,
prints a human-readable summary AND (if available) calls the embedded AI
assistant to suggest safe cleanup targets.

It does NOT modify global state itself, and it is safe to import lazily
from Computer_Main_Centre.py.
"""

from __future__ import annotations

import os
import shlex
import json
from pathlib import Path
from typing import Dict, Any, List, Tuple


def _fmt_bytes(n: int) -> str:
    """Human-readable bytes."""
    units = ["B", "KB", "MB", "GB", "TB"]
    x = float(n)
    for u in units:
        if x < 1024.0 or u == units[-1]:
            if u == "B":
                return f"{int(x)} {u}"
            return f"{x:0.1f} {u}"
        x /= 1024.0
    return f"{x:.1f} TB"


def _iter_children(root: Path) -> List[Path]:
    try:
        return list(root.iterdir())
    except Exception:
        return []


def _folder_size(root: Path, max_depth: int, file_accumulator: List[Tuple[str, int]]) -> int:
    """
    Compute total size of a folder up to a relative depth limit.
    Also appends (path, size) for each file into file_accumulator.
    """
    total = 0
    root = root.resolve()
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            dir_path = Path(dirpath)
            try:
                rel = dir_path.relative_to(root)
                depth = len(rel.parts)
            except Exception:
                depth = 0

            if depth > max_depth:
                dirnames[:] = []
                continue

            for name in filenames:
                f = dir_path / name
                try:
                    st = f.stat()
                    size = st.st_size
                except Exception:
                    continue
                total += size
                file_accumulator.append((str(f), size))
    except Exception:
        # best-effort; ignore permission issues etc.
        pass
    return total


def _detect_junk_candidates(
    root: Path,
    top_folders: List[Tuple[str, int]],
    top_files: List[Tuple[str, int]],
) -> List[Dict[str, Any]]:
    """
    Heuristic junk detector.

    Very conservative: only suggests things that are *commonly* safe to clean, such as:
      - node_modules
      - __pycache__
      - .cache
      - Temp / tmp folders under user/AppData
      - Large archives in Downloads (zip/7z/rar/iso)
      - Huge log files

    Returns a list of dicts with:
      { "path": str, "bytes": int, "kind": "folder|file", "reason": str }
    """
    junk: List[Dict[str, Any]] = []

    def add(path: str, size: int, kind: str, reason: str):
        junk.append({"path": path, "bytes": size, "kind": kind, "reason": reason})

    root_str = str(root)
    root_lower = root_str.lower()

    # Folder-based patterns
    folder_patterns = [
        ("node_modules", "Dependency cache (node_modules)"),
        ("__pycache__", "Python bytecode cache (__pycache__)"),
        (".cache", "Tool/framework cache (.cache)"),
        ("\\temp\\", "Temporary folder (Temp)"),
        ("/temp/", "Temporary folder (Temp)"),
        ("\\tmp\\", "Temporary folder (tmp)"),
        ("/tmp/", "Temporary folder (tmp)"),
        ("shadercache", "Graphics / game shader cache"),
        ("crashdumps", "Crash dump files"),
        ("\\logs", "Log folder"),
        ("/logs", "Log folder"),
    ]

    downloads_words = ["\\downloads", "/downloads"]

    # Examine folders
    for path, size in top_folders:
        low = path.lower()
        for pattern, reason in folder_patterns:
            if pattern in low:
                add(path, size, "folder", reason)
                break
        else:
            # Extra rule: big folders directly under Downloads
            if any(w in low for w in downloads_words):
                if size > 200 * 1024 * 1024:  # > 200 MB
                    add(path, size, "folder", "Large folder inside Downloads (often safe to review/remove)")

    # File-based patterns
    archive_exts = {".zip", ".7z", ".rar", ".tar", ".gz", ".bz2", ".xz", ".iso", ".img"}
    log_exts = {".log"}

    for path, size in top_files:
        low = path.lower()
        ext = Path(path).suffix.lower()

        if ext in archive_exts:
            if any(w in low for w in downloads_words):
                add(path, size, "file", "Large archive in Downloads (e.g. installer/archive)")
        elif ext in log_exts and size > 10 * 1024 * 1024:  # > 10 MB logs
            add(path, size, "file", "Large log file (often safe to delete)")

    # Sort by size descending
    junk.sort(key=lambda x: x["bytes"], reverse=True)
    return junk


def _build_summary(
    root: Path,
    total_bytes: int,
    folder_sizes: List[Tuple[str, int]],
    file_sizes: List[Tuple[str, int]],
    junk_candidates: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Create a compact JSON-able summary for the AI."""
    return {
        "root": str(root),
        "total_bytes": total_bytes,
        "top_folders": [
            {"path": p, "bytes": int(sz)} for (p, sz) in folder_sizes
        ],
        "top_files": [
            {"path": p, "bytes": int(sz)} for (p, sz) in file_sizes
        ],
        "junk_candidates": junk_candidates,
    }


def _print_summary(
    p,
    rich: bool,
    root: Path,
    depth: int,
    total_bytes: int,
    folders: List[Tuple[str, int]],
    files: List[Tuple[str, int]],
):
    """Pretty-prints the scan result using CMC's printer."""
    header = f"Analyzing disk usage in {root} (depth={depth})..."
    if rich:
        p(f"[bold yellow]📂 {header}[/bold yellow]")
    else:
        p(f"📂 {header}")
    if total_bytes > 0:
        if rich:
            p(f"[cyan]Total size (approx):[/cyan] {_fmt_bytes(total_bytes)}")
        else:
            p(f"Total size (approx): {_fmt_bytes(total_bytes)}")

    if folders:
        p("[bold]Top folders:[/bold]" if rich else "Top folders:")
        for path, size in folders:
            # Show only the last component relative to root for readability
            name = Path(path)
            try:
                name = name.relative_to(root)
            except Exception:
                pass
            p(f"  {_fmt_bytes(size):>8}  {name}")
    if files:
        p("[bold]Largest files:[/bold]" if rich else "Largest files:")
        for path, size in files:
            name = Path(path)
            try:
                name = name.relative_to(root)
            except Exception:
                pass
            p(f"  {_fmt_bytes(size):>8}  {name}")


def op_space(command: str, cwd: Path, state: Dict[str, Any], macros: Dict[str, str], p, rich: bool) -> None:
    """
    Entry point used by CMC.

    Parameters
    ----------
    command:
        Full user input line, e.g. "space", "space 'C:/Users/Wiggo' depth 3 report"
    cwd:
        Current working directory (Path).
    state:
        Shared STATE dict from CMC (can be used later to persist info).
    macros:
        Shared MACROS dict (passed through to AI for better context).
    p:
        CMC print function (handles Rich / plain output).
    rich:
        Whether Rich formatting is enabled.
    """

    # ----- Parse arguments -----
    # Strip leading "space"
    rest = command.strip()[len("space"):].strip()

    # Defaults
    target = cwd
    depth = 2
    make_report = False

    if rest:
        try:
            tokens = shlex.split(rest)
        except ValueError:
            tokens = rest.split()

        path_set = False
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            low = tok.lower()
            if low == "depth" and i + 1 < len(tokens):
                try:
                    depth = int(tokens[i + 1])
                except ValueError:
                    pass
                i += 2
                continue
            if low == "report":
                make_report = True
                i += 1
                continue
            if low == "full":
                depth = 4
                i += 1
                continue

            if not path_set:
                target = Path(tok)
                if not target.is_absolute():
                    target = (cwd / target).resolve()
                path_set = True
                i += 1
                continue

            # Unrecognized extra token -> ignore for now
            i += 1
    else:
        target = cwd

    # Clamp depth to something sensible
    if depth < 1:
        depth = 1
    if depth > 6:
        depth = 6

    if not target.exists():
        p(f"[red]Path not found:[/red] {target}" if rich else f"Path not found: {target}")
        return
    if not target.is_dir():
        p(f"[red]Not a folder:[/red] {target}" if rich else f"Not a folder: {target}")
        return

    # ----- Scan folder -----
    file_acc: List[Tuple[str, int]] = []
    folder_sizes: List[Tuple[str, int]] = []

    total_bytes = 0

    # Only measure immediate children of target for "Top folders"
    for child in _iter_children(target):
        if child.is_dir():
            size = _folder_size(child, max_depth=depth - 1, file_accumulator=file_acc)
            folder_sizes.append((str(child), size))
            total_bytes += size
        elif child.is_file():
            try:
                sz = child.stat().st_size
            except Exception:
                sz = 0
            file_acc.append((str(child), sz))
            total_bytes += sz

    # Sort and trim
    folder_sizes.sort(key=lambda x: x[1], reverse=True)
    file_acc.sort(key=lambda x: x[1], reverse=True)

    top_folders = folder_sizes[:10]
    top_files = file_acc[:10]

    # Detect junk candidates
    junk_candidates = _detect_junk_candidates(target, top_folders, top_files)

    # Store in state for possible future use
    try:
        state["last_space_scan"] = _build_summary(
            target,
            total_bytes,
            top_folders,
            top_files,
            junk_candidates,
        )
    except Exception:
        pass

    # Print summary
    _print_summary(p, rich, target, depth, total_bytes, top_folders, top_files)

    # Optional: write report
    if make_report:
        report_path = target / "CMC_space_report.txt"
        try:
            with report_path.open("w", encoding="utf-8") as f:
                f.write(json.dumps(state.get("last_space_scan", {}), indent=2))
            p(f"[green]Wrote report:[/green] {report_path}" if rich else f"Wrote report: {report_path}")
        except Exception as e:
            p(f"[red]Failed to write report:[/red] {e}" if rich else f"Failed to write report: {e}")

    # ----- AI integration (optional) -----
    try:
        from assistant_core import run_ai_assistant  # type: ignore
    except Exception:
        return  # AI not available, skip

    # Ask user before running AI
    prompt_user = "Run AI cleanup suggestions? (y/n): "
    try:
        ans = input(prompt_user).strip().lower()
    except KeyboardInterrupt:
        return
    except Exception:
        ans = "n"

    if ans not in ("y", "yes"):
        return

    # --- If confirmed, run the AI ---
    try:
        summary = state.get("last_space_scan")
        if not summary:
            return

        prompt = (
            "You are a cautious disk cleanup assistant for a Windows user.\n"
            "You are given a JSON summary of disk usage inside a folder:\n"
            "  - root folder\n"
            "  - total size\n"
            "  - top folders\n"
            "  - largest files\n"
            "  - pre-flagged junk_candidates\n\n"
            "Rules:\n"
            "  - NEVER suggest deleting system folders (Windows, Program Files, Drivers, etc.).\n"
            "  - NEVER suggest deleting installed applications, Steam games, IDEs, or tools.\n"
            "  - Prefer recommending cleanup of:\n"
            "      * Temp / cache folders\n"
            "      * node_modules / dependency caches\n"
            "      * log files\n"
            "      * large installer archives in Downloads\n"
            "  - Keep responses short, bullet-point style.\n\n"
            f"Here is the JSON summary:\n{json.dumps(summary, indent=2)}\n\n"
            "Now return ONLY safe cleanup suggestions."
        )

        reply = run_ai_assistant(prompt, str(target), state, macros)

        if reply:
            if rich:
                p("[cyan]🧠 AI cleanup suggestions:[/cyan]")
            else:
                p("AI cleanup suggestions:")
            p(reply)

    except Exception as e:
        p(f"[yellow]AI cleanup step failed:[/yellow] {e}" if rich else f"AI cleanup step failed: {e}")

