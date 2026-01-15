# CMC_Update.py
from __future__ import annotations

import datetime
import json
import shutil
import ssl
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Optional, Tuple
from urllib.request import Request, urlopen

# -------------------------------------------------------------------
# CMC Self Updater
#
# Modes:
#  1) If CMC folder is a git repo and git exists -> hard reset to origin
#  2) Otherwise -> download GitHub zip and FULL sync (including deletions)
#
# Safety:
#  - Makes a backup zip first
#  - Skips local generated folders/files (like .ai_helper, CentreIndex, etc.)
# -------------------------------------------------------------------

DEFAULT_REPO = "Wiglol/Computer_Main_Centre_Public"
DEFAULT_REMOTE = f"https://github.com/{DEFAULT_REPO}.git"

DATA_DIR = Path.home() / ".ai_helper"
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = DATA_DIR / "cmc_update.json"

# Never touch these local/generated items during zip-sync
SKIP_TOPLEVEL = {
    ".ai_helper",
    ".git",
    "__pycache__",
    "CentreIndex",
}

SKIP_FILES = {
    "paths.db",
}

SKIP_GLOBS = [
    "centre_index*.json",
    "*.log",
    "*.tmp",
]

# ---------------------------
# Small helpers
# ---------------------------

def _ssl_ctx(ssl_verify: bool):
    if ssl_verify:
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _http_bytes(url: str, ssl_verify: bool, timeout: int = 60) -> bytes:
    req = Request(
        url,
        headers={
            "User-Agent": "CMC-Updater",
            "Accept": "application/vnd.github+json",
        },
    )
    with urlopen(req, timeout=timeout, context=_ssl_ctx(ssl_verify)) as r:
        return r.read()


def _http_json(url: str, ssl_verify: bool) -> dict:
    raw = _http_bytes(url, ssl_verify=ssl_verify, timeout=20)
    return json.loads(raw.decode("utf-8", errors="replace"))


def _load_state() -> dict:
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        pass
    return {}


def _save_state(d: dict) -> None:
    try:
        STATE_FILE.write_text(json.dumps(d, indent=2), encoding="utf-8")
    except Exception:
        pass


def _should_skip(rel: Path) -> bool:
    # rel is path relative to repo root
    parts = rel.parts
    if parts and parts[0] in SKIP_TOPLEVEL:
        return True

    name = rel.name
    if name in SKIP_FILES:
        return True

    from fnmatch import fnmatch
    s = str(rel).replace("\\", "/")
    for g in SKIP_GLOBS:
        if fnmatch(name, g) or fnmatch(s, g):
            return True

    return False


def _backup_zip(folder: Path) -> Path:
    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out = folder.parent / f"CMC_backup_{ts}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in folder.rglob("*"):
            if p.is_dir():
                continue
            rel = p.relative_to(folder)
            if _should_skip(rel):
                continue
            zf.write(p, arcname=str(rel).replace("\\", "/"))
    return out


def _prune_empty_dirs(root: Path) -> None:
    # remove empty dirs bottom-up, but never remove skip toplevels
    for d in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda x: len(x.parts), reverse=True):
        try:
            rel = d.relative_to(root)
        except Exception:
            continue
        if not rel.parts:
            continue
        if rel.parts[0] in SKIP_TOPLEVEL:
            continue
        try:
            if not any(d.iterdir()):
                d.rmdir()
        except Exception:
            pass


def _sync_tree_full(src_root: Path, dst_root: Path) -> Tuple[int, int]:
    """
    FULL sync:
      - copy/overwrite all files from src -> dst (excluding skip)
      - delete files in dst that do not exist in src (excluding skip)
    Returns: (copied_files, deleted_files)
    """
    src_files: set[str] = set()
    for p in src_root.rglob("*"):
        if p.is_dir():
            continue
        rel = p.relative_to(src_root)
        if _should_skip(rel):
            continue
        src_files.add(str(rel).replace("\\", "/"))

    dst_files: set[str] = set()
    for p in dst_root.rglob("*"):
        if p.is_dir():
            continue
        rel = p.relative_to(dst_root)
        if _should_skip(rel):
            continue
        dst_files.add(str(rel).replace("\\", "/"))

    # deletions first (so removed upstream is removed locally)
    deleted = 0
    for rel_s in sorted(dst_files - src_files):
        target = dst_root / rel_s
        try:
            target.unlink()
            deleted += 1
        except Exception:
            # if locked/permission, ignore and continue
            pass

    # copy/overwrite
    copied = 0
    for rel_s in sorted(src_files):
        sp = src_root / rel_s
        dp = dst_root / rel_s
        dp.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(sp, dp)
        copied += 1

    _prune_empty_dirs(dst_root)
    return copied, deleted


# ---------------------------
# GitHub helpers
# ---------------------------

def _github_default_branch(repo: str, ssl_verify: bool) -> str:
    try:
        info = _http_json(f"https://api.github.com/repos/{repo}", ssl_verify=ssl_verify)
        b = info.get("default_branch")
        return b if isinstance(b, str) and b else "main"
    except Exception:
        return "main"


def _github_latest_sha(repo: str, branch: str, ssl_verify: bool) -> Optional[str]:
    try:
        data = _http_json(f"https://api.github.com/repos/{repo}/commits/{branch}", ssl_verify=ssl_verify)
        sha = (data or {}).get("sha")
        return sha if isinstance(sha, str) and sha else None
    except Exception:
        return None


def _download_repo_zip(repo: str, branch: str, out_path: Path, ssl_verify: bool) -> None:
    # codeload is usually more reliable than API zipball (no API rate limiting)
    url = f"https://codeload.github.com/{repo}/zip/refs/heads/{branch}"
    raw = _http_bytes(url, ssl_verify=ssl_verify, timeout=120)
    out_path.write_bytes(raw)


def _extract_zip(zip_path: Path, td: Path) -> Path:
    out_dir = td / "unzipped"
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(out_dir)

    # zip contains a single top folder
    top_dirs = [x for x in out_dir.iterdir() if x.is_dir()]
    if not top_dirs:
        raise RuntimeError("Unzip failed: no folder found inside zip.")
    return top_dirs[0]


# ---------------------------
# Git-based updater
# ---------------------------

def _git_installed() -> bool:
    return bool(shutil.which("git"))


def _git_run(args: list[str], cwd: Path) -> Tuple[int, str]:
    r = subprocess.run(["git"] + args, cwd=str(cwd), text=True, capture_output=True)
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    combined = (out + ("\n" + err if err else "")).strip()
    return r.returncode, combined


def _git_repo_root(folder: Path) -> Optional[Path]:
    if not (folder / ".git").exists():
        return None
    rc, out = _git_run(["rev-parse", "--show-toplevel"], cwd=folder)
    if rc == 0 and out and "fatal" not in out.lower():
        p = Path(out.strip())
        if p.exists():
            return p
    return folder


def _git_origin_branch(repo_root: Path) -> str:
    # Try to read origin/HEAD -> origin/main
    rc, out = _git_run(["symbolic-ref", "refs/remotes/origin/HEAD"], cwd=repo_root)
    if rc == 0 and out:
        # refs/remotes/origin/main
        parts = out.strip().split("/")
        if parts:
            return parts[-1]
    return "main"


def _git_set_origin(repo_root: Path, remote_url: str) -> None:
    rc, _ = _git_run(["remote", "get-url", "origin"], cwd=repo_root)
    if rc == 0:
        _git_run(["remote", "set-url", "origin", remote_url], cwd=repo_root)
    else:
        _git_run(["remote", "add", "origin", remote_url], cwd=repo_root)


def _git_clean_excludes_args() -> list[str]:
    # protect local data even if untracked
    excludes = [
        ".ai_helper",
        "CentreIndex",
        "paths.db",
        "centre_index*.json",
        "*.log",
        "*.tmp",
    ]
    args = ["clean", "-fd"]
    for e in excludes:
        args += ["-e", e]
    return args


def _git_check(p, repo_root: Path) -> None:
    _git_set_origin(repo_root, DEFAULT_REMOTE)
    branch = _git_origin_branch(repo_root)

    rc, out = _git_run(["fetch", "--all", "--prune"], cwd=repo_root)
    if rc != 0:
        p(f"⚠️ git fetch failed:\n{out}")
        return

    rc1, head = _git_run(["rev-parse", "HEAD"], cwd=repo_root)
    rc2, remote = _git_run(["rev-parse", f"origin/{branch}"], cwd=repo_root)
    if rc1 != 0 or rc2 != 0:
        p("⚠️ Could not resolve local/remote commit.")
        return

    rc3, behind = _git_run(["rev-list", "--count", f"HEAD..origin/{branch}"], cwd=repo_root)
    rc4, ahead = _git_run(["rev-list", "--count", f"origin/{branch}..HEAD"], cwd=repo_root)

    p(f"Repo (git): {DEFAULT_REPO} ({branch})")
    p(f"Local:  {head[:8]}")
    p(f"Remote: {remote[:8]}")

    if rc3 == 0 and rc4 == 0:
        b = int(behind.strip() or "0")
        a = int(ahead.strip() or "0")
        if b == 0 and a == 0:
            p("✅ You are up to date.")
        elif b > 0 and a == 0:
            p(f"🆕 Update available ({b} commits behind). Run: cmc update")
        else:
            p(f"⚠️ Diverged (ahead {a}, behind {b}). `cmc update` will hard-reset to remote.")
    else:
        # fallback: status output
        _, status = _git_run(["status", "-uno"], cwd=repo_root)
        p(status)


def _git_apply(p, repo_root: Path) -> bool:
    _git_set_origin(repo_root, DEFAULT_REMOTE)
    branch = _git_origin_branch(repo_root)

    # backup
    try:
        backup = _backup_zip(repo_root)
        p(f"🧷 Backup created: {backup}")
    except Exception as e:
        p(f"⚠️ Backup failed (continuing anyway): {e}")

    # fetch
    rc, out = _git_run(["fetch", "--all", "--prune"], cwd=repo_root)
    if rc != 0:
        p(f"❌ git fetch failed:\n{out}")
        return False

    # stash if dirty (so user can recover if they want)
    rc, dirty = _git_run(["status", "--porcelain"], cwd=repo_root)
    if rc == 0 and dirty.strip():
        _git_run(["stash", "push", "-u", "-m", "CMC auto-update backup"], cwd=repo_root)
        p("🧷 Local changes were stashed (git stash).")

    # hard reset to remote
    rc, out = _git_run(["checkout", "-B", branch, f"origin/{branch}"], cwd=repo_root)
    if rc != 0:
        p(f"❌ git checkout failed:\n{out}")
        return False

    rc, out = _git_run(["reset", "--hard", f"origin/{branch}"], cwd=repo_root)
    if rc != 0:
        p(f"❌ git reset failed:\n{out}")
        return False

    # remove untracked stuff (but exclude local data)
    rc, out = _git_run(_git_clean_excludes_args(), cwd=repo_root)
    if rc != 0:
        p(f"⚠️ git clean had issues:\n{out}")

    rc, head = _git_run(["rev-parse", "HEAD"], cwd=repo_root)
    if rc == 0 and head:
        st = _load_state()
        st["installed_sha"] = head.strip()
        st["installed_at"] = datetime.datetime.now().isoformat(timespec="seconds")
        st["method"] = "git"
        _save_state(st)

    p("✅ Update applied via git hard-reset.")
    p("⚠️ Restart CMC to load the new code (close and re-open).")
    return True


# ---------------------------
# Public API used by main CMC
# ---------------------------

def cmc_update_check(p, cmc_folder: Path, repo: str = DEFAULT_REPO, ssl_verify: bool = True) -> None:
    cmc_folder = Path(cmc_folder).resolve()

    # Prefer git check if possible
    if _git_installed() and (cmc_folder / ".git").exists():
        root = _git_repo_root(cmc_folder) or cmc_folder
        _git_check(p, root)
        return

    # Zip/API check
    branch = _github_default_branch(repo, ssl_verify=ssl_verify)
    latest = _github_latest_sha(repo, branch, ssl_verify=ssl_verify)
    state = _load_state()
    installed = state.get("installed_sha")

    if not latest:
        p("⚠️ Could not check GitHub (no internet / blocked / rate limit).")
        if installed:
            p(f"Installed: {str(installed)[:8]}")
        return

    p(f"Repo: {repo} ({branch})")
    p(f"Latest:    {latest[:8]}")
    if installed:
        p(f"Installed: {str(installed)[:8]}")
        if str(installed) == str(latest):
            p("✅ You are up to date.")
        else:
            p("🆕 Update available. Run: cmc update")
    else:
        p("ℹ️ No installed version recorded yet. Run: cmc update")


def cmc_update_apply(p, cmc_folder: Path, repo: str = DEFAULT_REPO, ssl_verify: bool = True) -> None:
    cmc_folder = Path(cmc_folder).resolve()

    # Prefer git apply if possible
    if _git_installed() and (cmc_folder / ".git").exists():
        root = _git_repo_root(cmc_folder) or cmc_folder
        ok = _git_apply(p, root)
        if ok:
            return
        p("⚠️ Git update failed, falling back to ZIP update...")

    # ZIP apply (full sync including deletions)
    branch = _github_default_branch(repo, ssl_verify=ssl_verify)
    latest = _github_latest_sha(repo, branch, ssl_verify=ssl_verify)

    state = _load_state()
    installed = state.get("installed_sha")
    if latest and installed and str(installed) == str(latest):
        p("✅ Already up to date.")
        return

    p(f"⬇️ Downloading update from {repo} ({branch}) ...")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        zip_path = td / "cmc_update.zip"

        try:
            _download_repo_zip(repo, branch, zip_path, ssl_verify=ssl_verify)
        except Exception as e:
            p(f"❌ Download failed: {e}")
            return

        try:
            src_root = _extract_zip(zip_path, td)
        except Exception as e:
            p(f"❌ Unzip failed: {e}")
            return

        # Backup
        try:
            backup = _backup_zip(cmc_folder)
            p(f"🧷 Backup created: {backup}")
        except Exception as e:
            p(f"⚠️ Backup failed (continuing anyway): {e}")

        # Full sync
        try:
            copied, deleted = _sync_tree_full(src_root, cmc_folder)
            p(f"✅ Synced files: copied/overwritten {copied}, deleted {deleted}")
        except Exception as e:
            p(f"❌ Sync failed: {e}")
            return

    if latest:
        state["installed_sha"] = latest
    state["installed_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    state["method"] = "zip"
    _save_state(state)

    p("✅ Update applied.")
    p("⚠️ Restart CMC to load the new code (close and re-open).")
