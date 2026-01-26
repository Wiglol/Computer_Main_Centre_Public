# CMC_Update.py
import json
import os
import shutil
import tempfile
import zipfile
import datetime
from pathlib import Path
from urllib.request import Request, urlopen
import subprocess

# Change this if your “official update source” repo changes
DEFAULT_REPO = "Wiglol/Computer-Main-Centre-Public"
DEFAULT_BRANCH = "main"

DATA_DIR = Path.home() / ".ai_helper"
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = DATA_DIR / "cmc_update.json"

# These are "local junk / generated" files we should NOT overwrite during update
SKIP_NAMES = {
    ".ai_helper",
    ".git",
    "__pycache__",
    "CentreIndex",         # your index db lives here in some builds
}
SKIP_FILES = {
    "paths.db",
}
SKIP_GLOBS = [
    "centre_index*.json",
    "*.log",
    "*.tmp",
]

def _http_json(url: str) -> dict:
    req = Request(url, headers={"User-Agent": "CMC-Updater"})
    with urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))

def _http_download(url: str, out_path: Path) -> None:
    req = Request(url, headers={"User-Agent": "CMC-Updater"})
    with urlopen(req, timeout=60) as r, open(out_path, "wb") as f:
        shutil.copyfileobj(r, f)

def _load_state() -> dict:
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

def _save_state(d: dict) -> None:
    try:
        STATE_FILE.write_text(json.dumps(d, indent=2), encoding="utf-8")
    except Exception:
        pass
        
def _write_update_notes_version(cmc_folder: Path, version: str) -> None:
    """
    Ensures UpdateNotes/VERSION.txt exists and is set to `version`.
    LATEST.txt is NOT modified (you maintain that in the repo).
    """
    try:
        notes_dir = Path(cmc_folder) / "UpdateNotes"
        notes_dir.mkdir(parents=True, exist_ok=True)

        ver_file = notes_dir / "VERSION.txt"
        ver_file.write_text(str(version).strip() + "\n", encoding="utf-8")
    except Exception:
        # Never fail the update because of notes bookkeeping
        pass


def _latest_sha(repo: str = DEFAULT_REPO, branch: str = DEFAULT_BRANCH) -> str | None:
    # GitHub API: latest commit on branch
    url = f"https://api.github.com/repos/{repo}/commits/{branch}"
    try:
        data = _http_json(url)
        sha = (data or {}).get("sha")
        return sha if isinstance(sha, str) and sha else None
    except Exception:
        return None

def _should_skip(rel: Path) -> bool:
    # top-level skip folders
    parts = rel.parts
    if parts and parts[0] in SKIP_NAMES:
        return True

    name = rel.name
    if name in SKIP_FILES:
        return True

    # glob checks
    from fnmatch import fnmatch
    s = str(rel).replace("\\", "/")
    for g in SKIP_GLOBS:
        if fnmatch(name, g) or fnmatch(s, g):
            return True

    return False

def _backup_folder(src: Path) -> Path:
    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out = src.parent / f"CMC_backup_{ts}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in src.rglob("*"):
            if p.is_dir():
                continue
            rel = p.relative_to(src)
            if _should_skip(rel):
                continue
            zf.write(p, arcname=str(rel).replace("\\", "/"))
    return out

def _copy_tree(src_root: Path, dst_root: Path) -> None:
    for p in src_root.rglob("*"):
        rel = p.relative_to(src_root)
        if _should_skip(rel):
            continue

        dst = dst_root / rel
        if p.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst)
            
            
def _git_installed() -> bool:
    return shutil.which("git") is not None


def _git_run(args, cwd: Path) -> str:
    return subprocess.run(
        ["git"] + args,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    ).stdout.strip()


def _git_update(p, cmc_folder: Path) -> None:
    # Backup first
    try:
        backup = _backup_folder(cmc_folder)
        p(f"🧷 Backup created: {backup}")
    except Exception as e:
        p(f"⚠️ Backup failed (continuing anyway): {e}")

    _git_run(["fetch", "--all", "--prune"], cmc_folder)

    # Hard reset to origin/main
    _git_run(["reset", "--hard", "origin/main"], cmc_folder)

    # Clean untracked files (except important stuff)
    _git_run(
        ["clean", "-fd", "-e", ".ai_helper", "-e", "CentreIndex", "-e", "paths.db"],
        cmc_folder,
    )

    # Record installed SHA
    sha = _git_run(["rev-parse", "HEAD"], cmc_folder)
    state = _load_state()
    state["installed_sha"] = sha
    _save_state(state)

    p("✅ Update applied via git.")
    p("⚠️ Restart CMC to load the new code.")


def cmc_update_check(p, repo: str = DEFAULT_REPO, branch: str = DEFAULT_BRANCH) -> None:
    state = _load_state()
    installed = state.get("installed_sha")

    latest = _latest_sha(repo, branch)
    if not latest:
        p("⚠️ Could not check GitHub (no internet / blocked / rate limit).")
        if installed:
            p(f"Installed: {installed[:8]}")
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

def cmc_update_apply(
    p,
    cmc_folder: Path,
    repo: str = DEFAULT_REPO,
    branch: str = DEFAULT_BRANCH,
) -> None:
    cmc_folder = Path(cmc_folder).resolve()

    # ==========================================================
    # 1) PREFER GIT IF THIS IS A GIT REPOSITORY
    # ==========================================================
    if shutil.which("git") and (cmc_folder / ".git").exists():
        try:
            # Backup first
            try:
                backup = _backup_folder(cmc_folder)
                p(f"🧷 Backup created: {backup}")
            except Exception as e:
                p(f"⚠️ Backup failed (continuing anyway): {e}")

            subprocess.run(
                ["git", "fetch", "--all", "--prune"],
                cwd=cmc_folder,
                check=True,
            )

            subprocess.run(
                ["git", "reset", "--hard", f"origin/{branch}"],
                cwd=cmc_folder,
                check=True,
            )

            subprocess.run(
                [
                    "git",
                    "clean",
                    "-fd",
                    "-e",
                    ".ai_helper",
                    "-e",
                    "CentreIndex",
                    "-e",
                    "paths.db",
                ],
                cwd=cmc_folder,
                check=True,
            )

            sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=cmc_folder,
                text=True,
            ).strip()

            state = _load_state()
            state["installed_sha"] = sha
            _save_state(state)
            
            _write_update_notes_version(cmc_folder, sha)

            p("✅ Update applied via git.")
            p("⚠️ Restart CMC to load the new code (close and re-open).")
            return

        except Exception as e:
            p(f"❌ Git update failed: {e}")
            return

    # ==========================================================
    # 2) ZIP / GITHUB API FALLBACK (NON-GIT INSTALLS)
    # ==========================================================
    latest = _latest_sha(repo, branch)
    if not latest:
        p("❌ Update failed: could not get latest version info from GitHub.")
        p("Tip: try again later or check your internet.")
        return

    state = _load_state()
    installed = state.get("installed_sha")
    if installed and str(installed) == str(latest):
        p("✅ Already up to date.")
        return

    zip_url = f"https://api.github.com/repos/{repo}/zipball/{branch}"

    p(f"⬇️ Downloading update from {repo} ({branch}) ...")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        zip_path = td / "cmc_update.zip"

        try:
            _http_download(zip_url, zip_path)
        except Exception as e:
            p(f"❌ Download failed: {e}")
            return

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(td / "unzipped")
        except Exception as e:
            p(f"❌ Unzip failed: {e}")
            return

        # zipball has a single top folder like repo-commitsha/
        unz = td / "unzipped"
        top_dirs = [x for x in unz.iterdir() if x.is_dir()]
        if not top_dirs:
            p("❌ Unzip failed: no folder found inside zip.")
            return
        src_root = top_dirs[0]

        # Backup
        try:
            backup = _backup_folder(cmc_folder)
            p(f"🧷 Backup created: {backup}")
        except Exception as e:
            p(f"⚠️ Backup failed (continuing anyway): {e}")

        # Copy over
        try:
            _copy_tree(src_root, cmc_folder)
        except Exception as e:
            p(f"❌ Copy failed: {e}")
            return

    state["installed_sha"] = latest
    _save_state(state)
    
    _write_update_notes_version(cmc_folder, latest)

    p("✅ Update applied.")
    p("⚠️ Restart CMC to load the new code (close and re-open).")
