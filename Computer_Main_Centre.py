
#!/usr/bin/env python3
# ==============================================
#  Computer Main Centre  — Local AI Command Console
#  - Batch mode, Dry-Run, SSL toggle
#  - Rich UI if available
#  - Navigation + search (with progress)
#  - File ops (create/read/write/rename/copy/move/delete/zip/unzip/open/explore/run/backup)
#  - Internet download (1 GB cap, SSL on/off, progress)
#  - Log + basic undo (move/rename)
#  - Macros (add / run / list / delete / clear) persisted to %USERPROFILE%\.ai_helper\macros.json
# ==============================================

import os, sys, re, fnmatch, shutil, zipfile, subprocess, datetime, time, json, threading
from pathlib import Path
from urllib.parse import urlparse

# ---------- Optional dependencies ----------
RICH = False
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn, DownloadColumn, TransferSpeedColumn
    from rich.prompt import Confirm
    from rich.box import HEAVY
    RICH = True
    console = Console()
except Exception:
    class _Dummy:
        def print(self, *a, **k): print(*a)
    console = _Dummy()

HAVE_REQUESTS = False
try:
    import requests
    HAVE_REQUESTS = True
except Exception:
    pass

# ---------- Global state ----------
HOME = Path.home()
CWD = Path.cwd()
STATE = {
    "batch": False,
    "dry_run": False,
    "ssl_verify": True,
    "history": [str(CWD)]
}
LOG = []    # list of strings

# ---------- Java + Local Path Index Integration ----------

JAVA_VERSIONS = {
    "8":  r"C:\Program Files\Eclipse Adoptium\jdk-8.0.462.8-hotspot",
    "17": r"C:\Program Files\Eclipse Adoptium\jdk-17.0.16.8-hotspot",
    "21": r"C:\Program Files\Eclipse Adoptium\jdk-21.0.8.9-hotspot",
}

# Config directory (same as before)
CFG_DIR = Path(os.path.expandvars(r"%USERPROFILE%\\.ai_helper"))
CFG_DIR.mkdir(parents=True, exist_ok=True)
JAVA_CFG = CFG_DIR / "java.json"


# ---------- Apply Java Environment ----------
def _apply_java_env(java_home: str):
    if not java_home:
        return
    bin_path = str(Path(java_home) / "bin")
    os.environ["JAVA_HOME"] = java_home
    path = os.environ.get("PATH", "")
    parts = path.split(os.pathsep)
    # Remove old Java entries from PATH
    parts = [p for p in parts if p and "Java" not in p and "\\jdk-" not in p and "/jdk-" not in p]
    parts.insert(0, bin_path)
    os.environ["PATH"] = os.pathsep.join(parts)


# ---------- Java detection + config ----------
def detect_java_version() -> str:
    """Detects Java version from java -version, registry, or JAVA_HOME."""
    # Try java -version
    try:
        out = subprocess.check_output(["java", "-version"], stderr=subprocess.STDOUT, text=True, shell=True)
        m = re.search(r'version\s+"([^"]+)"', out)
        if not m:
            m = re.search(r"(\d+)", out)
        if m:
            full = m.group(1).strip()
            if full.startswith("1."):  # Java 8 format like "1.8.0_462"
                return full.split(".")[1]
            return full.split(".")[0]
    except Exception:
        pass

    # Try registry
    try:
        reg_out = subprocess.check_output('reg query "HKCU\\Environment" /v JAVA_HOME', shell=True, text=True, stderr=subprocess.DEVNULL)
        m2 = re.search(r"JAVA_HOME\s+REG_SZ\s+(.+)", reg_out)
        if m2:
            java_home = m2.group(1).strip()
            for ver in ("8", "17", "21"):
                if f"jdk-{ver}" in java_home or ver in java_home:
                    return ver
    except Exception:
        pass

    # Try environment variable
    java_home = os.environ.get("JAVA_HOME", "")
    if java_home:
        for ver in ("8", "17", "21"):
            if f"jdk-{ver}" in java_home or ver in java_home:
                return ver

    return "?"


def load_java_cfg():
    """Load persisted Java info or auto-detect + refresh environment."""
    ver = "?"
    home = None
    try:
        if JAVA_CFG.exists():
            data = json.loads(JAVA_CFG.read_text(encoding="utf-8"))
            ver = str(data.get("version", "?"))
            home = data.get("home", "")
            if home and Path(home).exists():
                _apply_java_env(home)
    except Exception:
        pass

    # Always re-detect actual version live
    detected = detect_java_version()
    if detected and detected != "?":
        ver = detected

    STATE["java_version"] = ver
    if home:
        os.environ["JAVA_HOME"] = home


def save_java_cfg(ver: str, home: str):
    """Save and immediately refresh Java version display."""
    try:
        JAVA_CFG.write_text(
            json.dumps({"version": ver, "home": home}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        os.environ["JAVA_HOME"] = home
        _apply_java_env(home)
        STATE["java_version"] = detect_java_version()
    except Exception as e:
        print(f"[WARN] Could not save Java config: {e}")


# --- Auto-load + detect on startup ---
load_java_cfg()
STATE["java_version"] = detect_java_version()



# ---------- GitHub Integration (Wizard) ----------
import base64

GIT_CFG = CFG_DIR / "github.json"  # persists your PAT locally

def _git_run(cmd: str, cwd: str = None):
    """Run git shell command and return combined output or raise on error."""
    try:
        r = subprocess.run(cmd, cwd=cwd, shell=True, text=True,
                           capture_output=True, check=True)
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        return (out + ("\n" + err if err else "")).strip() or "(done)"
    except subprocess.CalledProcessError as e:
        out = (e.stdout or "").strip()
        err = (e.stderr or "").strip()
        raise RuntimeError((out + ("\n" + err if err else "")).strip())

def _git_token():
    """Read/write GitHub Personal Access Token (classic) in ~/.ai_helper/github.json."""
    if GIT_CFG.exists():
        try:
            data = json.loads(GIT_CFG.read_text(encoding="utf-8"))
            tok = data.get("token", "").strip()
            if tok and tok.startswith("ghp_"):
                return tok
        except Exception:
            pass
    # Ask once
    tok = input("Enter your GitHub Personal Access Token (classic): ").strip()
    if tok:
        GIT_CFG.write_text(json.dumps({"token": tok}, indent=2), encoding="utf-8")
        return tok
    return None

def _git_username_from_token(token: str) -> str | None:
    """Call GitHub API to get the username associated with this token."""
    try:
        import urllib.request, urllib.error
        req = urllib.request.Request(
            "https://api.github.com/user",
            headers={"Authorization": f"token {token}",
                     "User-Agent": "CMC-GitAssistant"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            js = json.loads(resp.read().decode("utf-8"))
            return js.get("login")
    except Exception:
        return None

def _git_api_create_repo(token: str, name: str) -> tuple[bool, str]:
    """Create repo via API. Returns (ok, message_or_url)."""
    try:
        import urllib.request, urllib.error
        body = json.dumps({"name": name, "auto_init": False}).encode("utf-8")
        req = urllib.request.Request(
            "https://api.github.com/user/repos",
            data=body,
            headers={
                "Authorization": f"token {token}",
                "Content-Type": "application/json",
                "User-Agent": "CMC-GitAssistant"
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            js = json.loads(resp.read().decode("utf-8"))
            return True, js.get("html_url", "")
    except Exception as e:
        try:
            err = e.read().decode("utf-8")  # type: ignore[attr-defined]
        except Exception:
            err = str(e)
        return False, err

def _git_ensure_repo_initialized(root: Path) -> None:
    """Run git init if .git missing."""
    if not (root / ".git").exists():
        _git_run("git init", cwd=str(root))

def _git_set_remote(root: Path, remote_url: str) -> None:
    """Set or update origin remote."""
    try:
        _git_run("git remote show origin", cwd=str(root))
        _git_run(f"git remote set-url origin {remote_url}", cwd=str(root))
    except Exception:
        _git_run(f"git remote add origin {remote_url}", cwd=str(root))

def _git_ensure_main_branch(root: Path) -> None:
    try:
        _git_run("git rev-parse --verify main", cwd=str(root))
    except Exception:
        # create or rename to main
        try:
            _git_run("git branch -M main", cwd=str(root))
        except Exception:
            _git_run("git checkout -b main", cwd=str(root))

def _git_warn_large_files(root: Path) -> list[str]:
    """Return list of tracked files > 100 MB, to prevent GitHub push failure."""
    big = []
    try:
        out = _git_run("git ls-files -s", cwd=str(root))
        files = [line.split()[-1] for line in out.splitlines() if line.strip()]
        for f in files:
            fp = root / f
            if fp.exists() and fp.is_file() and fp.stat().st_size > 100 * 1024 * 1024:
                big.append(f)
    except Exception:
        pass
    return big

def _gitignore_add(root: Path, patterns: list[str]) -> None:
    gi = root / ".gitignore"
    lines = []
    if gi.exists():
        lines = gi.read_text(encoding="utf-8", errors="ignore").splitlines()
    for ptn in patterns:
        if ptn not in lines:
            lines.append(ptn)
    gi.write_text("\n".join(lines) + "\n", encoding="utf-8")

def handle_git_commands(s: str, low: str) -> bool:
    """
    Handle all /git* commands. Return True if matched.
    Commands:
      /gitsetup "RepoName"
      /gitlink "https://github.com/USER/REPO.git"
      /gitupdate "message"
      /gitpull
      /gitstatus
      /gitlog
      /gitbranch
      /gitignore add <pattern>
      /gitclean
      /gitfix
      /gitdoctor
      /gitlfs setup
    """
    root = Path.cwd()
    # Only react to /git... commands
    if not low.startswith("/git"):
        return False

    # /gitignore add <pattern>
    m = re.match(r'^/gitignore\s+add\s+(.+)$', s, re.I)
    if m:
        patterns = [pt.strip() for pt in m.group(1).split(",") if pt.strip()]
        _gitignore_add(root, patterns)
        p(f"Added to .gitignore: {', '.join(patterns)}")
        return True

    # /gitclean — remove common local junk from tracking
    if low == "/gitclean":
        try:
            # untrack big/local caches (keeps files on disk)
            _git_run("git rm --cached -r __pycache__", cwd=str(root))
        except Exception:
            pass
        _gitignore_add(root, ["__pycache__/"])
        p("Cleaned git cache entries and updated .gitignore.")
        return True

       # /gitlfs setup
    if low == "/gitlfs setup":
        messages = []
        try:
            _git_run("git lfs install", cwd=str(root))
            _git_run('git lfs track "*.db" "*.zip" "*.jar" "*.exe"', cwd=str(root))
            messages.append("✅ Git LFS initialized for *.db, *.zip, *.jar, *.exe")
            messages.append("💡 Remember to commit .gitattributes after setup.")
        except Exception as e:
            messages.append(f"❌ LFS setup failed: {e}")

        text = "\n".join(messages)
        if RICH:
            from rich.panel import Panel
            console.print(Panel(text, title="Git LFS Setup", border_style="cyan", padding=(0, 1)))
        else:
            print(text)
        return True


    # /gitdoctor — diagnostics

    if low == "/gitdoctor":
        msgs = []
        try:
            _git_run("git --version")
            msgs.append("git: OK")
        except Exception as e:
            msgs.append(f"git: {e}")
        if (root / ".git").exists():
            msgs.append(".git: exists")
            # remote?
            try:
                r = _git_run("git remote -v", cwd=str(root))
                msgs.append("remote:\n" + r)
            except Exception as e:
                msgs.append(f"remote: {e}")
            # branch?
            try:
                b = _git_run("git rev-parse --abbrev-ref HEAD", cwd=str(root))
                msgs.append(f"branch: {b}")
            except Exception as e:
                msgs.append(f"branch: {e}")
        else:
            msgs.append(".git: missing")
        tok = "present" if _git_token() else "missing"
        msgs.append(f"token: {tok}")
        text = "\n".join(msgs)

        if RICH:
            from rich.panel import Panel
            console.print(Panel(text, title="Git Doctor", border_style="cyan", padding=(0, 1)))
        else:
            print(text)
        return True


        # /gitfix — auto-repair common issues
    if low == "/gitfix":
        messages = []
        try:
            _git_ensure_repo_initialized(root)
            _git_ensure_main_branch(root)
            messages.append("✅ Repo initialized and main branch verified.")
        except Exception as e:
            messages.append(f"❌ ensure repo failed: {e}")
        try:
            _git_run("git rev-parse --abbrev-ref --symbolic-full-name @{u}", cwd=str(root))
            messages.append("✅ Upstream already set.")
        except Exception:
            messages.append("⚠️ Upstream missing — run `/gitlink \"https://github.com/USER/REPO.git\"` then `/gitupdate`.")
        
        text = "\n".join(messages)
        if RICH:
            from rich.panel import Panel
            console.print(Panel(text, title="Git Fix", border_style="cyan", padding=(0, 1)))
        else:
            print(text)
        return True


    # /gitlink "https://github.com/USER/REPO.git"
    m = re.match(r'^/gitlink\s+"([^"]+)"$', s, re.I)
    if m:
        url = m.group(1).strip()
        try:
            _git_ensure_repo_initialized(root)
            _git_ensure_main_branch(root)
            _git_set_remote(root, url)
            p(f"Remote origin set to: {url}")
        except Exception as e:
            p(f"[red]❌ gitlink failed:[/red] {e}")
        return True


    # /gitsetup "RepoName"
    m = re.match(r'^/gitsetup\s+"([^"]+)"$', s, re.I)
    if m:
        repo = m.group(1).strip()
        p(f"🔧 Setting up GitHub repo '{repo}' ...")
        tok = _git_token()
        if not tok:
            p("[red]❌ No token provided.[/red]")
            return True
        user = _git_username_from_token(tok) or "unknown"
        ok, msg = _git_api_create_repo(tok, repo)
        if not ok:
            p(f"❌ GitHub API error: {msg}")
            return True
        # Link and initial commit/push
        try:
            _git_ensure_repo_initialized(root)
            _git_ensure_main_branch(root)
            remote_url = f"https://github.com/{user}/{repo}.git"
            _git_set_remote(root, remote_url)
            # sane defaults
            _gitignore_add(root, ["paths.db", "centre_index*.json", "__pycache__/"])
            _git_run("git add .", cwd=str(root))
            _git_run('git commit -m "Initial commit"', cwd=str(root))
            # Warn large files
            big = _git_warn_large_files(root)
            if big:
                p("⚠️ Large tracked files (>100MB) detected:")
                for b in big:
                    p(f"  - {b}")
                p("Add them to .gitignore or set up LFS before pushing.")
                return True
            # first push
            _git_run("git branch -M main", cwd=str(root))
            _git_run("git push --set-upstream origin main", cwd=str(root))
            p("✅ Repository created and pushed!")
        except Exception as e:
            p(f"[red]❌ gitsetup failed:[/red] {e}")
        return True

    # /gitupdate "message"
    m = re.match(r'^/gitupdate\s+"([^"]+)"$', s, re.I)
    if m:
        msg = m.group(1).strip()
        try:
            _git_ensure_repo_initialized(root)
            _git_ensure_main_branch(root)
            # ensure remote exists (won’t overwrite if present)
            try:
                _git_run("git remote show origin", cwd=str(root))
            except Exception:
                p("No remote set. Use /gitlink \"https://github.com/USER/REPO.git\" first.")
                return True
            # large file guard
            big = _git_warn_large_files(root)
            if big:
                p("⚠️ Large tracked files (>100MB) detected (push will fail on GitHub):")
                for b in big:
                    p(f"  - {b}")
                p("Tip: /gitignore add paths.db, then commit again.")
                return True
            _git_run("git add .", cwd=str(root))
            # commit (skip-empty)
            try:
                _git_run(f'git commit -m "{msg}"', cwd=str(root))
            except Exception as e:
                if "nothing to commit" not in str(e).lower():
                    raise
                p("Nothing to commit.")
            # push (auto set upstream if needed)
            try:
                _git_run("git push", cwd=str(root))
            except Exception as e:
                if "has no upstream branch" in str(e):
                    _git_run("git push --set-upstream origin main", cwd=str(root))
                else:
                    raise
            p("✅ Updated GitHub.")
        except Exception as e:
            p(f"[red]❌ gitupdate failed:[/red] {e}")
        return True

    # /gitpull
    if low == "/gitpull":
        try:
            _git_run("git pull", cwd=str(root))
            p("✅ Pulled latest changes.")
        except Exception as e:
            p(f"[red]❌ gitpull failed:[/red] {e}")
        return True

    # /gitstatus
    if low == "/gitstatus":
        try:
            out = _git_run("git status", cwd=str(root))
            p(out)
        except Exception as e:
            p(f"[red]❌ gitstatus failed:[/red] {e}")
        return True

    # /gitlog
    if low == "/gitlog":
        try:
            out = _git_run("git log --oneline -n 10", cwd=str(root))
            p("🕓 Recent commits:\n" + out)
        except Exception as e:
            p(f"[red]❌ gitlog failed:[/red] {e}")
        return True

    # /gitbranch
    if low == "/gitbranch":
        try:
            out = _git_run("git branch -a", cwd=str(root))
            p(out)
        except Exception as e:
            p(f"[red]❌ gitbranch failed:[/red] {e}")
        return True

    return True  # matched some /git* pattern but fell through




try:
    import runpy
    PATH_INDEX_LOCAL = r"C:\Users\Wiggo\Desktop\CentreAPI\path_index_local.py"
    _mod_pathindex = runpy.run_path(PATH_INDEX_LOCAL)
    _qpaths = _mod_pathindex.get("query_paths")
    _qcount = _mod_pathindex.get("count_paths")
    _qbuild = _mod_pathindex.get("rebuild_index")
    _DB_DEFAULT = _mod_pathindex.get("DEFAULT_DB")
except Exception as _e:
    _qpaths = _qcount = _qbuild = _DB_DEFAULT = None

UNDO = []  # stack of reversible actions

DATA_DIR = HOME / ".ai_helper"
DATA_DIR.mkdir(exist_ok=True)
MACROS_FILE = DATA_DIR / "macros.json"
if not MACROS_FILE.exists():
    MACROS_FILE.write_text("{}", encoding="utf-8")


# ---------- Helpers ----------
def p(x):
    if RICH:
        console.print(x)
    else:
        print(re.sub(r"\[/?[a-z]+\]", "", str(x)))

def lc_size(n):
    try:
        n = int(n)
    except Exception:
        return "?"
    units = ["B","KB","MB","GB","TB"]
    i = 0
    while n >= 1024 and i < len(units)-1:
        n /= 1024.0; i += 1
    return f"{n:.2f} {units[i]}"

def resolve(path: str) -> Path:
    path = path.replace("\\", "/")
    if re.match(r"^[A-Za-z]:/", path):
        return Path(path)
    return (CWD / path).resolve()

def confirm(msg: str) -> bool:
    if STATE["batch"]:
        if RICH:
            p(f"[dim](auto)[/dim] {msg}")
        else:
            print(f"(auto) {msg}")
        return True
    if STATE["dry_run"]:
        p(f"[yellow]DRY-RUN {msg.splitlines()[0].lower()} ->[/yellow] {msg.splitlines()[-1]}")
        return False
    if RICH:
        console.print(Panel(msg, title="Confirm", border_style="cyan"))
        return Confirm.ask("Proceed?")
    else:
        ans = input(f"{msg}\nProceed? (y/n): ").strip().lower()
        return ans.startswith("y")

def log_action(s: str):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    LOG.append(f"[{ts}] {s}")

def push_undo(kind, **kw):
    UNDO.append({"kind": kind, **kw})


# ---------- Header ----------

def show_header():
    """
    Clean cyan header box with aligned borders and a clear structure.
    Displays:
      • Computer Main Centre title
      • Batch / SSL / Dry-Run status
      • A helpful hint for new users
      • Active Java version (auto-detected)
    """
    title_line = "Computer Main Centre"
    status = (
        f"Batch: {'ON' if STATE['batch'] else 'OFF'}  |  "
        f"SSL: {'ON' if STATE['ssl_verify'] else 'OFF'}  |  "
        f"Dry-Run: {'OFF' if not STATE['dry_run'] else 'ON'}"
    )
    hint_line = "🧭 Explore commands with ‘help’"
    # ensure Java line updates dynamically
    java_version = STATE.get("java_version") or detect_java_version()
    java_line = f"Java: {java_version} (Active)"
    content = f"Local command console\n{status}\n{hint_line}\n{java_line}"

    if RICH:
        console.print(f"[bold]{title_line}[/bold]")
        console.print(Panel.fit(content, border_style="cyan"))
    else:
        print(title_line)
        print(content)


def status_panel():
    """
    Displays current Centre status and toggles.
    """
    status = (
        f"Batch: {'ON' if STATE['batch'] else 'OFF'}  |  "
        f"SSL: {'ON' if STATE['ssl_verify'] else 'OFF'}  |  "
        f"Dry-Run: {'OFF' if not STATE['dry_run'] else 'ON'}"
    )
    if RICH:
        panel = Panel.fit(status, title="Computer Main Centre", border_style="cyan")
        console.print(panel)
    else:
        print(status)





# ---------- Navigation ----------
def op_pwd():
    p(str(CWD))

def op_cd(path):
    global CWD
    tgt = resolve(path)
    if tgt.exists() and tgt.is_dir():
        CWD = tgt
        STATE["history"].append(str(CWD))
    else:
        p(f"[red]❌ Not a directory:[/red] {tgt}" if RICH else f"Not a directory: {tgt}")

def op_back():
    hist = STATE["history"]
    if len(hist) >= 2:
        hist.pop()
        op_cd(hist[-1])
    else:
        p("[yellow]No previous directory.[/yellow]" if RICH else "No previous directory.")

def op_home():
    op_cd(str(HOME))

def op_list(path=None, depth=1, only=None, pattern=None):
    root = resolve(path) if path else CWD
    rows = []
    try:
        for base, dirs, files in os.walk(root):
            lvl = Path(base).relative_to(root).parts
            if len(lvl) > depth: continue
            if only in (None, "dirs"):
                for d in dirs:
                    full = str(Path(base)/d)
                    if pattern and not fnmatch.fnmatch(d, pattern): continue
                    rows.append((full, "dir"))
            if only in (None, "files"):
                for f in files:
                    full = str(Path(base)/f)
                    if pattern and not fnmatch.fnmatch(f, pattern): continue
                    rows.append((full, "file"))
        if RICH:
            t = Table(title=f"Listing: {root}")
            t.add_column("Path", overflow="fold")
            t.add_column("Type", width=6)
            for r in rows:
                t.add_row(*r)
            console.print(t)
        else:
            for r in rows:
                print(f"{r[0]}\t{r[1]}")
    except Exception as e:
        p(f"[red]❌ {e}[/red]" if RICH else f"Error: {e}")

# ---------- Search with progress ----------
def _walk_with_progress(root: Path):
    total_dirs = 0
    total_files = 0
    for _, dirs, files in os.walk(root):
        total_dirs += len(dirs)
        total_files += len(files)
    if RICH:
        prog = Progress(TextColumn("[progress.description]{task.description}"),
                        BarColumn(), TextColumn("{task.completed}/{task.total}"),
                        transient=True, console=console)
        task = None
        with prog:
            task = prog.add_task("Scanning", total=total_files or 1)
            for base, dirs, files in os.walk(root):
                for f in files:
                    prog.update(task, advance=1)
                    yield base, f
    else:
        scanned = 0
        for base, dirs, files in os.walk(root):
            for f in files:
                scanned += 1
                if scanned % 1000 == 0:
                    print(f"Scanning... {scanned} files")
                yield base, f

def find_name(name: str):
    root = CWD
    hits = []
    for base, f in _walk_with_progress(root):
        if name.lower() in f.lower():
            hits.append(str(Path(base)/f))
    show_hits(hits)

def find_ext(ext: str):
    if not ext.startswith("."): ext = "." + ext
    root = CWD
    hits = []
    for base, f in _walk_with_progress(root):
        if f.lower().endswith(ext.lower()):
            hits.append(str(Path(base)/f))
    show_hits(hits)

def recent_paths(path=None, limit=20):
    root = resolve(path) if path else CWD
    records = []
    for base, f in _walk_with_progress(root):
        fp = Path(base)/f
        try:
            m = fp.stat().st_mtime
            records.append((m, str(fp)))
        except Exception:
            pass
    records.sort(reverse=True)
    show_hits([b for _, b in records[:limit]])

def biggest_paths(path=None, limit=20):
    root = resolve(path) if path else CWD
    records = []
    for base, f in _walk_with_progress(root):
        fp = Path(base)/f
        try:
            s = fp.stat().st_size
            records.append((s, str(fp)))
        except Exception:
            pass
    records.sort(reverse=True)
    show_hits([b for _, b in records[:limit]], show_size=True)

def search_text(text: str):
    root = CWD
    hits = []
    for base, f in _walk_with_progress(root):
        fp = Path(base)/f
        try:
            if Path(f).suffix.lower() in (".txt",".md",".json",".cfg",".ini",".log",".xml",".py",".zs",".mcmeta",".properties"):
                s = (Path(base)/f).read_text(encoding="utf-8", errors="ignore")
                if text.lower() in s.lower():
                    hits.append(str(Path(base)/f))
        except Exception:
            pass
    show_hits(hits)

def show_hits(hits, show_size=False):
    if RICH:
        t = Table(title=f"Results ({len(hits)})")
        t.add_column("Path", overflow="fold")
        if show_size: t.add_column("Size", justify="right")
        for h in hits[:1000]:
            if show_size:
                try: t.add_row(h, lc_size(Path(h).stat().st_size))
                except Exception: t.add_row(h, "?")
            else:
                t.add_row(h)
        console.print(t)
    else:
        for h in hits:
            print(h)

# ---------- File ops ----------
def op_create_file(name, folder, text=None):
    tgt_folder = resolve(folder)
    tgt_folder.mkdir(parents=True, exist_ok=True)
    fp = tgt_folder / name
    msg = f"Create file:\n  {fp}" if text is None else f"Create file:\n  {fp}\nwith text ({len(text)} chars)"
    if confirm(msg):
        if STATE["dry_run"]:
            p(f"[yellow]DRY-RUN create file ->[/yellow] {fp}" if RICH else f"DRY-RUN create {fp}")
            return
        fp.write_text(text or "", encoding="utf-8")
        log_action(f"CREATED FILE {fp}")
        p(f"[green]✅ Created:[/green] {fp}" if RICH else f"Created: {fp}")

def op_create_folder(name, parent):
    par = resolve(parent)
    fp = par / name
    if confirm(f"Create folder:\n  {fp}"):
        if STATE["dry_run"]:
            p(f"[yellow]DRY-RUN create folder ->[/yellow] {fp}")
            return
        fp.mkdir(parents=True, exist_ok=True)
        log_action(f"CREATED FOLDER {fp}")
        p(f"[green]✅ Created folder:[/green] {fp}")

def op_write(path, text):
    fp = resolve(path)
    if confirm(f"Write:\n  {fp}\n{text[:100]}..."):
        if STATE["dry_run"]:
            p(f"[yellow]DRY-RUN write ->[/yellow] {fp}")
            return
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(text, encoding="utf-8")
        log_action(f"WROTE {fp}")
        p(f"[green]✅ Written:[/green] {fp}")

def op_read(path, head=None):
    fp = resolve(path)
    if not fp.exists() or not fp.is_file():
        p(f"[red]❌ Not found:[/red] {fp}" if RICH else f"Not found: {fp}")
        return
    content = fp.read_text(encoding="utf-8", errors="replace")
    if head is not None:
        content = "\n".join(content.splitlines()[:head])
    if RICH:
        console.print(Panel(content, title=str(fp)))
    else:
        print(content)

def op_move(src, dst):
    s = resolve(src); d = resolve(dst)
    d.mkdir(parents=True, exist_ok=True)
    tgt = d / s.name
    if confirm(f"Move:\n  {s}\n→ {tgt}"):
        if STATE["dry_run"]:
            p(f"[yellow]DRY-RUN move ->[/yellow] {s} → {tgt}")
            return
        shutil.move(str(s), str(tgt))
        push_undo("move", src=str(tgt), dst=str(s))  # reverse
        log_action(f"MOVED {s} -> {tgt}")
        p("[green]✅ Moved[/green]" if RICH else "Moved")

def op_copy(src, dst):
    s = resolve(src); d = resolve(dst)
    if confirm(f"Copy:\n  {s}\n→ {d}"):
        if STATE["dry_run"]:
            p(f"[yellow]DRY-RUN copy ->[/yellow] {s} → {d}")
            return
        d.mkdir(parents=True, exist_ok=True)
        if s.is_dir():
            shutil.copytree(s, d / s.name, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)
        log_action(f"COPIED {s} -> {d}")
        p(f"[green]✅ Copied to[/green] {d}" if RICH else f"Copied to {d}")

def op_rename(src, newname):
    s = resolve(src)
    t = s.parent / newname
    if confirm(f"Rename:\n  {s}\n→ {t}"):
        if STATE["dry_run"]:
            p(f"[yellow]DRY-RUN rename ->[/yellow] {s} → {t}")
            return
        os.rename(s, t)
        push_undo("rename", src=str(t), dst=str(s))  # reverse
        log_action(f"RENAMED {s} -> {t}")
        p("[green]✅ Renamed[/green]" if RICH else "Renamed")

def op_delete(path):
    s = resolve(path)
    if confirm(f"Delete:\n  {s}"):
        if STATE["dry_run"]:
            p(f"[yellow]DRY-RUN delete ->[/yellow] {s}")
            return
        if s.is_dir():
            shutil.rmtree(s)
        elif s.exists():
            s.unlink()
        log_action(f"DELETED {s}")
        p(f"🗑️ Deleted {s}")

def _zip_dir_to(zf: zipfile.ZipFile, base: Path, root: Path):
    """Write all files under root to zf, with paths relative to base directory."""
    for r, dirs, files in os.walk(root):
        for f in files:
            fp = Path(r)/f
            zf.write(fp, fp.relative_to(base))

def op_zip(path):
    s = resolve(path)
    out = s.with_suffix(".zip") if s.is_file() else (s.parent / f"{s.name}.zip")
    if confirm(f"Zip:\n  {s}\n→ {out}"):
        if STATE["dry_run"]:
            p(f"[yellow]DRY-RUN zip ->[/yellow] {s} → {out}")
            return
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            if s.is_dir():
                _zip_dir_to(zf, s.parent, s)
            else:
                zf.write(s, s.name)
        log_action(f"ZIPPED {s} -> {out}")
        p(f"[green]✅ Zipped to:[/green] {out}" if RICH else f"Zipped to: {out}")

def op_unzip(zip_path, dest):
    zp = resolve(zip_path); d = resolve(dest)
    if confirm(f"Unzip:\n  {zp}\n→ {d}"):
        if STATE["dry_run"]:
            p(f"[yellow]DRY-RUN unzip ->[/yellow] {zp} → {d}")
            return
        d.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zp, "r") as zf:
            zf.extractall(d)
        log_action(f"UNZIPPED {zp} -> {d}")
        p(f"[green]✅ Unzipped to:[/green] {d}" if RICH else f"Unzipped to: {d}")

def op_open(path):
    fp = resolve(path)
    try:
        if not STATE["dry_run"]:
            os.startfile(str(fp))
            log_action(f"OPENED {fp}")
    except Exception as e:
        p(f"[red]❌ {e}[/red]" if RICH else f"Error: {e}")

def op_explore(path):
    fp = resolve(path)
    try:
        target = fp if fp.is_dir() else fp.parent
        if not STATE["dry_run"]:
            subprocess.Popen(["explorer", str(target)])
            log_action(f"EXPLORED {target}")
            p(f"📂 Explorer opened: {target}")
    except Exception as e:
        p(f"[red]❌ Error:[/red] {e}" if RICH else f"Error: {e}")

def op_backup(src, dest):
    # Create zip of src into dest/world_YYYY-MM-DD_HH-MM-SS.zip
    s = resolve(src); d = resolve(dest)
    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    name = f"{s.name}_{ts}.zip" if s.is_dir() else f"{s.stem}_{ts}.zip"
    out = d / name
    if confirm(f"Backup (zip):\n  {s}\n→ {out}"):
        if STATE["dry_run"]:
            p(f"[yellow]DRY-RUN zip ->[/yellow] {out}")
            return
        d.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            if s.is_dir():
                _zip_dir_to(zf, s.parent, s)
            else:
                zf.write(s, s.name)
        log_action(f"BACKUP_ZIP {s} -> {out}")
        p(f"[green]✅ Backup created:[/green] {out}")

def op_run(path):
    fp = resolve(path)
    if not fp.exists():
        p(f"[red]❌ Not found:[/red] {fp}" if RICH else f"Not found: {fp}")
        return
    if confirm(f"Run script:\n  {fp}"):
        if not STATE["dry_run"]:
            try:
                subprocess.Popen([sys.executable, str(fp)], cwd=str(fp.parent))
                log_action(f"RUN {fp}")
            except Exception as e:
                p(f"[red]❌ {e}[/red]" if RICH else f"Error: {e}")

# ---------- Internet ops ----------
DOWNLOAD_CAP_BYTES = 1_000_000_000  # 1 GB

def filename_from_url(url):
    pth = urlparse(url).path
    fn = Path(pth).name or "download.bin"
    return fn

def op_open_url(url):
    try:
        if sys.platform.startswith("win"):
            os.startfile(url)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", url])
        else:
            subprocess.Popen(["xdg-open", url])
        log_action(f"OPEN_URL {url}")
    except Exception as e:
        p(f"[red]❌ {e}[/red]" if RICH else f"Error: {e}")

def op_download(url, dest_folder):
    dest = resolve(dest_folder)
    dest.mkdir(parents=True, exist_ok=True)
    fname = filename_from_url(url)
    out_path = dest / fname

    size_bytes = None
    if HAVE_REQUESTS:
        try:
            h = requests.head(url, allow_redirects=True, timeout=10, verify=STATE["ssl_verify"])
            if h.ok and "content-length" in h.headers:
                size_bytes = int(h.headers["content-length"])
        except Exception:
            size_bytes = None

    if size_bytes is not None and size_bytes > DOWNLOAD_CAP_BYTES:
        p(f"[red]❌ File exceeds 1 GB limit ({lc_size(size_bytes)}).[/red]" if RICH else "File exceeds 1 GB.")
        return

    label_size = lc_size(size_bytes) if size_bytes is not None else "unknown size"
    if not confirm(f"Download:\n  {url}\n→ {out_path}\nSize: {label_size}"):
        return

    try:
        if HAVE_REQUESTS:
            with requests.get(url, stream=True, timeout=30, verify=STATE["ssl_verify"]) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length", 0)) or size_bytes or 0
                if total and total > DOWNLOAD_CAP_BYTES:
                    p(f"[red]❌ File exceeds 1 GB limit during GET ({lc_size(total)}).[/red]" if RICH else "File exceeds 1 GB.")
                    return
                if RICH and total:
                    with Progress(
                        TextColumn("[progress.description]{task.description}"),
                        BarColumn(),
                        DownloadColumn(),
                        TransferSpeedColumn(),
                        TimeRemainingColumn(),
                        transient=True,
                        console=console
                    ) as prog, open(out_path, "wb") as f:
                        t = prog.add_task(f"Downloading {fname}", total=total)
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                prog.update(t, advance=len(chunk))
                else:
                    with open(out_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
        else:
            # urllib fallback
            import urllib.request, ssl
            req = urllib.request.Request(url)
            ctx = None
            if not STATE["ssl_verify"]:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(req, context=ctx) as response, open(out_path, "wb") as out:
                total = response.length or 0
                if total and total > DOWNLOAD_CAP_BYTES:
                    p("File exceeds 1 GB limit."); return
                block = 8192; downloaded = 0
                if RICH and total:
                    with Progress(TextColumn("[progress.description]{task.description}"), BarColumn(),
                                  DownloadColumn(), TransferSpeedColumn(), TimeRemainingColumn(),
                                  transient=True, console=console) as prog:
                        t = prog.add_task(f"Downloading {fname}", total=total or 1)
                        while True:
                            buf = response.read(block)
                            if not buf: break
                            downloaded += len(buf)
                            if downloaded > DOWNLOAD_CAP_BYTES:
                                p("File exceeds 1 GB limit during download.")
                                return
                            out.write(buf)
                            prog.update(t, advance=len(buf))
                else:
                    while True:
                        buf = response.read(block)
                        if not buf: break
                        downloaded += len(buf)
                        if downloaded > DOWNLOAD_CAP_BYTES:
                            p("File exceeds 1 GB limit during download."); return
                        out.write(buf)
        log_action(f"DOWNLOADED {url} -> {out_path}")
        p(f"[green]✅ Downloaded:[/green] {out_path}" if RICH else f"Downloaded: {out_path}")
        if confirm("📂 Open containing folder?"):
            op_explore(str(out_path.parent))
    except Exception as e:
        p(f"[red]❌ {e}[/red]" if RICH else f"Error: {e}")

def op_download_list(file_with_urls, dest_folder):
    fp = resolve(file_with_urls)
    if not fp.exists():
        p(f"[red]❌ Not found:[/red] {fp}" if RICH else f"Not found: {fp}")
        return
    urls = [line.strip() for line in fp.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]
    for u in urls:
        op_download(u, dest_folder)

# ---------- Log / Undo ----------
def op_log():
    if not LOG:
        p("[yellow]No log entries yet.[/yellow]" if RICH else "No log entries.")
        return
    if RICH:
        t = Table(title="Log")
        t.add_column("Entry", overflow="fold")
        for e in LOG[-200:]:
            t.add_row(e)
        console.print(t)
    else:
        for e in LOG[-200:]:
            print(e)

def op_undo():
    if not UNDO:
        p("[yellow]Nothing to undo.[/yellow]" if RICH else "Nothing to undo.")
        return
    step = UNDO.pop()
    try:
        if step["kind"] == "move":
            shutil.move(step["src"], step["dst"])
            p("[green]✅ Undid last move.[/green]" if RICH else "Undid move.")
        elif step["kind"] == "rename":
            os.rename(step["src"], step["dst"])
            p("[green]✅ Undid last rename.[/green]" if RICH else "Undid rename.")
        else:
            p("[yellow]Cannot undo this action.[/yellow]")
    except Exception as e:
        p(f"[red]❌ Undo failed:[/red] {e}" if RICH else f"Undo failed: {e}")

# ---------- Macros (persistent) ----------
def macros_load():
    try:
        if MACROS_FILE.exists():
            return json.loads(MACROS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

def macros_save(d: dict):
    MACROS_FILE.parent.mkdir(exist_ok=True)
    MACROS_FILE.write_text(json.dumps(d, indent=2), encoding="utf-8")

MACROS = macros_load()

def expand_vars(s: str) -> str:
    today = datetime.date.today().isoformat()
    now = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    home = str(Path.home())
    return s.replace("%DATE%", today).replace("%NOW%", now).replace("%HOME%", home)

def macro_add(name: str, text: str):
    name = name.strip()
    if not name: p("[red]Macro name required.[/red]"); return
    if not text.strip(): p("[red]Macro command text required.[/red]"); return
    if name in MACROS and not STATE["batch"]:
        if not confirm(f"Macro '{name}' exists. Overwrite?"):
            p("[yellow]Canceled.[/yellow]"); return
    MACROS[name] = text.replace(';', ' ; ')
    macros_save(MACROS)
    log_action(f"MACRO ADD {name} = {text}")
    p(f"[green]✅ Macro saved:[/green] {name}")

def macro_run(name: str):
    if name not in MACROS:
        p(f"[red]❌ Macro not found:[/red] {name}"); return
    p(f"[cyan]▶ Running macro:[/cyan] {name}") if RICH else print(f"> Running macro {name}")
    text = expand_vars(MACROS[name])
    for part in [t.strip() for t in re.split(r";\s*", text) if t.strip()]:
        handle_command(part)
    log_action(f"MACRO RUN {name}")

def macro_list():
    if not MACROS:
        p("[yellow]No macros saved.[/yellow]"); return
    if RICH:
        t = Table(title="Saved Macros")
        t.add_column("Name", style="cyan")
        t.add_column("Command(s)")
        for k, v in MACROS.items():
            t.add_row(k, v)
        p(t)
    else:
        for k, v in MACROS.items():
            print(f"- {k} = {v}")

def macro_delete(name: str):
    if name not in MACROS:
        p(f"[yellow]No such macro:[/yellow] {name}"); return
    del MACROS[name]
    macros_save(MACROS)
    log_action(f"MACRO DELETE {name}")
    p(f"[green]✅ Deleted macro:[/green] {name}")

def macro_clear():
    if not STATE["batch"]:
        if not confirm("Delete ALL macros?"):
            p("[yellow]Canceled.[/yellow]"); return
    MACROS.clear()
    macros_save(MACROS)
    log_action("MACRO CLEAR ALL")
    p("[green]✅ Cleared all macros.[/green]")

# ---------- Suggestions for partial commands ----------
COMMAND_HINTS = [
    "pwd","cd","back","home","list","info","find","findext","count","recent","biggest","search",
    "create file","create folder","write","read","move","copy","rename","delete",
    "zip","unzip","open","explore","backup","run",
    "download","downloadlist","open url",
    "batch on","batch off","dry-run on","dry-run off","ssl on","ssl off","status","log","undo",
    "macro add <name> = <commands>","macro run <name>","macro list","macro delete <name>","macro clear","help","exit"
]

def suggest_commands(s: str):
    s = s.strip().lower()
    cands = [h for h in COMMAND_HINTS if h.startswith(s)]
    if not cands:
        p(f"Unknown command: {s}")
        return
    if RICH:
        t = Table(title="Suggestions")
        t.add_column("Try")
        for c in cands[:10]:
            t.add_row(c)
        console.print(t)
    else:
        print("Suggestions:", ", ".join(cands[:10]))

# ---------- Handle Commands ----------
def handle_command(s: str):
    s = s.strip()
    if not s:
        return

    # 🩹 Fix for broken multi-line commands (AI sometimes splits "download ... to" and "C:/Downloads")
    if s.lower().endswith("to"):
        try:
            nxt = input("... ")  # continue input
            s = s + " " + nxt.strip()
        except EOFError:
            pass

    # Always normalize once the command string is ready
    low = s.lower()

    # Control
    if low in ("help", "?"):
        return show_help()
    if low == "status":
        status_panel(); return
    if low == "batch on":
        STATE["batch"] = True; log_action("BATCH ON"); p("Batch ON"); return
    if low == "batch off":
        STATE["batch"] = False; log_action("BATCH OFF"); p("Batch OFF"); return
    if low == "dry-run on":
        STATE["dry_run"] = True; p("Dry-Run ON"); return
    if low == "dry-run off":
        STATE["dry_run"] = False; p("Dry-Run OFF"); return
    if low == "ssl on":
        STATE["ssl_verify"] = True; p("SSL ON"); return
    if low == "ssl off":
        STATE["ssl_verify"] = False; p("⚠️ SSL verification OFF — allowing untrusted/expired certs"); return
    if low == "log":
        op_log(); return
    if low == "undo":
        op_undo(); return

    # Exit
    if low == "exit":
        sys.exit(0)

    # NEW: simple echo command (so macros can print messages)
    m = re.match(r'^echo\s+["“](.+?)["”]$', s, re.I)
    if m:
        p(m.group(1))
        return

    # Git commands (only trigger on /git...)
    if low.startswith("/git"):
        if handle_git_commands(s, low):
            return

    # Macros (inline)
    m = re.match(r"^macro\s+add\s+([A-Za-z0-9_\-]+)\s*=\s*(.+)$", s, re.I)
    if m:
        macro_add(m.group(1), m.group(2))
        return
    m = re.match(r"^macro\s+run\s+([A-Za-z0-9_\-]+)$", s, re.I)
    if m:
        macro_run(m.group(1))
        return
    m = re.match(r"^macro\s+delete\s+([A-Za-z0-9_\-]+)$", s, re.I)
    if m:
        macro_delete(m.group(1))
        return
    if re.match(r"^macro\s+list$", s, re.I):
        macro_list(); return
    if re.match(r"^macro\s+clear$", s, re.I):
        macro_clear(); return



    # Navigation
    if low == "pwd": op_pwd(); return
    m = re.match(r"^cd\s+'([^']+)'$", s, re.I)
    if m: op_cd(m.group(1)); return
    if low == "back": op_back(); return
    if low == "home": op_home(); return

    # List with optional args
    if low.startswith("list"):
        path = None
        depth = 1
        only = None
        pattern = None
        m = re.findall(r"(?:'([^']+)')|(\bdepth=\d+\b|\bonly=(?:files|dirs)\b|\bpattern=[^\s]+)", s)
        for grp in m:
            if grp[0]:
                path = grp[0]
            else:
                flag = grp[1]
                if flag.startswith("depth="):
                    depth = int(flag.split("=")[1])
                elif flag.startswith("only="):
                    only = flag.split("=")[1]
                elif flag.startswith("pattern="):
                    pattern = flag.split("=", 1)[1]
        op_list(path, depth, only, pattern)
        return

    # Java management
    if low == "java list":
        for k, v in JAVA_VERSIONS.items():
            tag = "(installed)" if Path(v).exists() else "(missing)"
            p(f"{k} -> {v} {tag}")
        return

    if low == "java version":
        home = os.environ.get("JAVA_HOME", "?")
        ver = STATE.get("java_version", "?")
        p(f"Active Java: {ver} ({home})")
        return

    if low == "java reload":
        try:
            # Refresh environment from registry
            home = subprocess.check_output(
                'reg query "HKCU\\Environment" /v JAVA_HOME',
                shell=True, text=True, stderr=subprocess.DEVNULL
            )
            m = re.search(r"JAVA_HOME\s+REG_SZ\s+(.+)", home)
            if m:
                new_home = m.group(1).strip()
                _apply_java_env(new_home)
                STATE["java_version"] = "?"
                save_java_cfg("?", new_home)
                p(f"🔄 Reloaded system Java from registry: {new_home}")
                p("Close/reopen CMC if version text doesn’t update immediately.")
            else:
                p("No JAVA_HOME found in registry.")
        except Exception as e:
            p(f"[WARN] Failed to reload Java: {e}")
        return




    m = re.match(r"^java\s+change\s+(\d+)$", s, re.I)
    if m:
        ver = m.group(1)
        home = JAVA_VERSIONS.get(ver)
        if not home or not Path(home).exists():
            p(f"Java {ver} not found at configured path.")
            return

        # --- Apply locally (for current CMC session) ---
        _apply_java_env(home)
        STATE["java_version"] = ver
        save_java_cfg(ver, home)

        # --- Apply system-wide via setx ---
        try:
            subprocess.run(
                ["setx", "JAVA_HOME", home],
                shell=True,
                check=True,
                text=True,
                capture_output=True,
            )

            bin_path = str(Path(home) / "bin")
            subprocess.run(
                ["setx", "PATH", f"%PATH%;{bin_path}"],
                shell=True,
                check=True,
                text=True,
                capture_output=True,
            )

            p(f"✅ Java {ver} set system-wide ({home})")
            p("⚠️ Close and reopen any CMD/PowerShell windows for it to take effect.")
        except Exception as e:
            p(f"[WARN] Could not update system PATH: {e}")

        return




    # Local index quick find
    m = re.match(r"^/qfind\s+(.+)$", s, re.I)
    if m and _qpaths:
        terms = m.group(1).strip()
        rows = _qpaths(_DB_DEFAULT, terms, 20)
        if not rows:
            p("No results."); return
        for pth, score in rows:
            p(f"{pth} ({score}%)")
        return
    if low == "/qcount" and _qcount:
        n = _qcount(_DB_DEFAULT)
        p(f"Indexed paths: {n:,}"); p(f"DB: {_DB_DEFAULT}"); return
    m = re.match(r"^/qbuild(?:\s+(.+))?$", s, re.I)
    if m and _qbuild:
        args = m.group(1).split() if m.group(1) else ["C:/Users/Wiggo","C","E","F"]
        _qbuild(_DB_DEFAULT, args)
        n = _qcount(_DB_DEFAULT) if _qcount else "?"
        p(f"[DONE] Indexed paths now: {n}")
        return
    # Info
    m = re.match(r"^info\s+'([^']+)'$", s, re.I)
    if m:
        fp = resolve(m.group(1))
        try:
            st = fp.stat()
            size = lc_size(st.st_size) if fp.is_file() else sum((p.stat().st_size for p in fp.rglob("*") if p.is_file()), 0)
            size_str = lc_size(size)
            modified = datetime.datetime.fromtimestamp(st.st_mtime)
            if RICH:
                console.print(Panel.fit(f"Name: {fp.name}\nType: {'file' if fp.is_file() else 'dir'}\nSize: {size_str}\nModified: {modified}",
                                        title=str(fp)))
            else:
                print(fp, size_str, modified)
        except Exception as e:
            p(f"[red]❌ {e}[/red]" if RICH else f"Error: {e}")
        return

    # Find / search
    m = re.match(r"^find\s+'([^']+)'$", s, re.I)
    if m: find_name(m.group(1)); return
    m = re.match(r"^findext\s+'?(\.[A-Za-z0-9]+)'?$", s, re.I)
    if m: find_ext(m.group(1)); return
    m = re.match(r"^recent(?:\s+'([^']+)')?$", s, re.I)
    if m: recent_paths(m.group(1), limit=20); return
    m = re.match(r"^biggest(?:\s+'([^']+)')?$", s, re.I)
    if m: biggest_paths(m.group(1), limit=20); return
    m = re.match(r"^search\s+'([^']+)'$", s, re.I)
    if m: search_text(m.group(1)); return

    # File ops
    m = re.match(r"^create\s+file\s+'([^']+)'\s+in\s+'([^']+)'(?:\s+with\s+text='(.*)')?$", s, re.I)
    if m: op_create_file(m.group(1), m.group(2), m.group(3)); return
    m = re.match(r"^create\s+folder\s+'([^']+)'\s+in\s+'([^']+)'$", s, re.I)
    if m: op_create_folder(m.group(1), m.group(2)); return
    m = re.match(r"^write\s+'([^']+)'\s+text='(.*)'$", s, re.I)
    if m: op_write(m.group(1), m.group(2)); return
    m = re.match(r"^read\s+'([^']+)'(?:\s+head=(\d+))?$", s, re.I)
    if m: op_read(m.group(1), int(m.group(2)) if m.group(2) else None); return
    m = re.match(r"^move\s+'([^']+)'\s+to\s+'([^']+)'$", s, re.I)
    if m: op_move(m.group(1), m.group(2)); return
    m = re.match(r"^copy\s+'([^']+)'\s+to\s+'([^']+)'$", s, re.I)
    if m: op_copy(m.group(1), m.group(2)); return
    m = re.match(r"^rename\s+'([^']+)'\s+to\s+'([^']+)'$", s, re.I)
    if m: op_rename(m.group(1), m.group(2)); return
    m = re.match(r"^delete\s+'([^']+)'$", s, re.I)
    if m: op_delete(m.group(1)); return
    m = re.match(r"^zip\s+'([^']+)'$", s, re.I)
    if m: op_zip(m.group(1)); return
    m = re.match(r"^unzip\s+'([^']+)'\s+to\s+'([^']+)'$", s, re.I)
    if m: op_unzip(m.group(1), m.group(2)); return
    m = re.match(r"^open\s+'([^']+)'$", s, re.I)
    if m: op_open(m.group(1)); return
    m = re.match(r"^explore\s+'([^']+)'$", s, re.I)
    if m: op_explore(m.group(1)); return
    m = re.match(r"^backup\s+'([^']+)'\s+'([^']+)'$", s, re.I)
    if m: op_backup(m.group(1), m.group(2)); return
    m = re.match(r"^run\s+'([^']+)'$", s, re.I)
    if m: op_run(m.group(1)); return

        # ---------- Internet (now supports both quoted and unquoted URLs/paths) ----------
    # downloadlist
    m = re.match(r"^downloadlist\s+(?:'([^']+)'|(\S+))\s+to\s+(?:'([^']+)'|(\S+))$", s, re.I)
    if m:
        src = m.group(1) or m.group(2)
        dest = m.group(3) or m.group(4)
        op_download_list(src, dest)
        return

    # download
    m = re.match(r"^download\s+(?:'([^']+)'|(\S+))\s+to\s+(?:'([^']+)'|(\S+))$", s, re.I)
    if m:
        src = m.group(1) or m.group(2)
        dest = m.group(3) or m.group(4)
        op_download(src, dest)
        return

    # open url
    m = re.match(r"^open\s+url\s+(?:'([^']+)'|(\S+))$", s, re.I)
    if m:
        url = m.group(1) or m.group(2)
        op_open_url(url)
        return


    # Unknown / partial
    suggest_commands(s)

# ---------- Help ----------

def show_help():
    content = (
"🧠 BASIC NAV — Move around, inspect folders/files\n"
"  pwd                      Show current directory\n"
"  cd 'C:/path'             Change directory\n"
"  back / home              Go back (history) or to user home\n"
"  list ['C:/path']         List contents (optional path)\n"
"  info 'path'              Show size, type, modified time\n"
"  find 'name'              Find files by name (within current folder)\n"
"  findext '.ext'           Find by file extension\n"
"  recent ['path']          Most recently modified files\n"
"  biggest ['path']         Biggest files/folders\n"
"  search 'text'            Search inside text-like files\n\n"
"────────────────────────────────────────────────────────\n\n"
"🗂 FILE OPS — Create, edit, move, copy, delete, zip\n"
"  create file 'name.txt' in 'C:/path'\n"
"  create folder 'Name' in 'C:/path'\n"
"  write 'C:/path/file.txt' text='hello'\n"
"  read  'C:/path/file.txt' [head=50]\n"
"  move  'C:/src' to 'C:/dst'\n"
"  copy  'C:/src' to 'C:/dst'\n"
"  rename 'C:/path/old' to 'NewName'\n"
"  delete 'C:/path'\n"
"  zip   'C:/path'              → creates C:/path.zip\n"
"  unzip 'C:/file.zip' to 'C:/dest'\n"
"  open  'C:/path/or/app.exe'   Open file/app\n"
"  explore 'C:/path'            Open in Explorer\n"
"  backup 'C:/src' 'C:/dest'    Zip into dest with timestamp\n"
"  run 'C:/path/script.py'      Run a Python script\n\n"
"────────────────────────────────────────────────────────\n\n"
"🌍 INTERNET — Download with 1 GB safety cap\n"
"  download 'https://...' to 'C:/Downloads'\n"
"  downloadlist 'C:/urls.txt' to 'C:/Downloads'\n"
"  open url 'https://example.com'\n\n"
"────────────────────────────────────────────────────────\n\n"
"🧰 MACROS (persistent) — Save and run command sequences\n"
"  macro add <name> = <commands>\n"
"  macro run <name>\n"
"  macro list\n"
"  macro delete <name>    macro clear\n"
"  Vars available: %DATE%, %NOW%, %HOME%\n\n"
"────────────────────────────────────────────────────────\n\n"
"⚙️ CONTROL — Toggles & utilities\n"
"  batch on | batch off        Auto-confirm prompts (skip Y/N)\n"
"  dry-run on | dry-run off    Preview actions without executing\n"
"  ssl on | ssl off            Toggle HTTPS certificate verification\n"
"  status                     Show current Computer Main Centre state (Batch / SSL / Dry-Run / Java)\n"
"  log                        Show operation history\n"
"  undo                       Undo last reversible action\n"
"  help                       Display this help menu\n"
"  exit                       Close Computer Main Centre\n\n"
"────────────────────────────────────────────────────────\n\n"
"☕ JAVA — Manage system-wide Java environment\n"
"  java list                   Show configured versions\n"
"  java version                Show currently active version and path\n"
"  java change <8|17|21>       Switch and persist system-wide\n"
"  java reload                 Reload system Java (re-read registry after change)\n\n"
"────────────────────────────────────────────────────────\n\n"
"🔎 LOCAL PATH INDEX (no server) — Instant search of your drives\n"
"  /qfind <terms> [limit]      Multi-word AND search (default limit 20)\n"
"  /qcount                     Show total indexed paths\n"
"  /qbuild [targets...]        Rebuild/refresh index (e.g. C:/Users/Wiggo C E F)\n\n"
"────────────────────────────────────────────────────────\n\n"
"🌐 GIT / GITHUB — Upload & sync projects\n"
"  /gitsetup \"RepoName\"          Create & push a brand-new GitHub repository\n"
"  /gitlink \"URL\"                Link this folder to an existing GitHub repo\n"
"  /gitupdate \"message\"          Add → Commit → Push recent changes\n"
"  /gitpull                       Pull and merge latest updates from GitHub\n"
"  /gitstatus                     Show working tree & staged changes\n"
"  /gitlog                        Show last 10 commit messages\n"
"  /gitbranch                     List or switch branches\n"
"  /gitignore add pattern         Add files or folders to .gitignore\n"
"  /gitclean                      Remove cached junk (like __pycache__)\n"
"  /gitfix                        Auto-repair repo (init / main / remote)\n"
"  /gitdoctor                     Diagnose setup, token, and remote issues\n"
"  /gitlfs setup                  Enable Git Large File Storage for big files\n\n"
"────────────────────────────────────────────────────────\n\n"
"💡 Examples\n"
"  /qfind atlauncher servers\n"
"  java change 17\n"
"  java reload\n"
"  backup 'C:/Users/Wiggo/Downloads' to 'C:/Backups'\n\n"
"Tips\n"
"  • Chain with semicolons: batch on; create file 'a.txt' in '.' with text='hi'; zip '.'; batch off\n"
"  • Paths can be relative to the current prompt directory."
    ).strip()

    if RICH:
        from rich.measure import Measurement
        width = Measurement.get(console, console.options, content).maximum + 4
        console.print(
            Panel(
                content,
                title="HELP",
                border_style="cyan",
                padding=(0, 1),
                expand=False,
                width=width
            )
        )
    else:
        print(content)






# ---------- Main loop ----------
def split_commands(line: str):
    parts = []
    buf = []
    q = None
    in_macro_add = False
    i = 0

    while i < len(line):
        ch = line[i]

        if q:
            # we're inside a quoted string
            if ch == q:
                q = None
            buf.append(ch)
        else:
            # not in quotes
            # detect "macro add" at the beginning of the line buffer
            if not in_macro_add:
                # look at the current buffer (trim leading spaces) in lowercase
                temp = "".join(buf).lstrip().lower()
                # once a line starts with "macro add", we stop splitting on ';'
                if temp.startswith("macro add"):
                    in_macro_add = True

            if ch in ("'", '"'):
                q = ch
                buf.append(ch)
            elif ch == ";" and not in_macro_add:
                # split commands on ';' unless we're in a macro add line
                parts.append("".join(buf).strip())
                buf = []
            else:
                buf.append(ch)

        i += 1

    if buf:
        parts.append("".join(buf).strip())
    return parts


import shlex

def main():
    global CWD
    show_header()
    while True:
        try:
            prompt = f"CMC>{str(CWD)}> "
            line = input(prompt)
        except (EOFError, KeyboardInterrupt):
            print(); break
        for part in split_commands(line):
            try:
                handle_command(part)
            except SystemExit:
                raise
            except Exception as e:
                p(f"[red]❌ Error:[/red] {e}" if RICH else f"Error: {e}")



if __name__ == "__main__":
    main()


# // test: autopublish propagation checkssssssssssssss
