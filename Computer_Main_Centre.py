
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

# ---------- Imports ----------
import readline, glob, os, sys, re, fnmatch, shutil, zipfile, subprocess, datetime, time, json, threading
from pathlib import Path
from urllib.parse import urlparse
# --- Path safeguard ---
import pathlib
Path = pathlib.Path  # force-restore original class in case it was shadowed


# Advanced prompt with live autocompletion
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.styles import Style


# ✅ Cross-platform readline import (for Windows autocompletion)
try:
    import readline
except ImportError:
    try:
        import pyreadline3 as readline
    except ImportError:
        readline = None


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




# ---------- Local Path Index (portable import) ----------
try:
    import runpy
    from pathlib import Path

    PATH_INDEX_LOCAL = Path(__file__).parent / "path_index_local.py"
    if not PATH_INDEX_LOCAL.exists():
        raise FileNotFoundError(f"Missing: {PATH_INDEX_LOCAL}")

    _mod_pathindex = runpy.run_path(str(PATH_INDEX_LOCAL))
    _qpaths  = _mod_pathindex.get("query_paths")
    _qcount  = _mod_pathindex.get("count_paths")
    _qbuild  = _mod_pathindex.get("rebuild_index")
    _DB_DEFAULT = _mod_pathindex.get("DEFAULT_DB")
except Exception as e:
    print(f"[WARN] Path-index module not loaded: {e}")
    _qpaths = _qcount = _qbuild = _DB_DEFAULT = None



UNDO = []  # stack of reversible actions

DATA_DIR = HOME / ".ai_helper"
DATA_DIR.mkdir(exist_ok=True)
MACROS_FILE = DATA_DIR / "macros.json"
if not MACROS_FILE.exists():
    MACROS_FILE.write_text("{}", encoding="utf-8")

# ---------- Aliases (persistent) ----------
ALIAS_FILE = Path(os.path.expanduser("~/.ai_helper/aliases.json"))
ALIASES = {}

def load_aliases():
    """Load alias list from ~/.ai_helper/aliases.json"""
    global ALIASES
    if ALIAS_FILE.exists():
        try:
            with open(ALIAS_FILE, "r", encoding="utf-8") as f:
                ALIASES = json.load(f)
        except Exception:
            ALIASES = {}
    else:
        ALIASES = {}

def save_aliases():
    """Save alias list"""
    ALIAS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(ALIAS_FILE, "w", encoding="utf-8") as f:
        json.dump(ALIASES, f, indent=2)

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
    hint_line = "Explore commands with ‘help’"
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
        
        
        # ---------- System Info ----------
def op_sysinfo(save_path=None):
    import platform, psutil, subprocess
    info = {}
    try:
        info["OS"] = f"{platform.system()} {platform.release()} ({platform.version()})"
        info["CPU"] = platform.processor() or "Unknown"
        info["Cores"] = psutil.cpu_count(logical=True)
        info["RAM"] = f"{round(psutil.virtual_memory().total / (1024**3), 1)} GB"
        # GPU via wmic
        try:
            gpu_out = subprocess.check_output(
                "wmic path win32_VideoController get name", shell=True, text=True
            )
            gpus = [g.strip() for g in gpu_out.splitlines() if g.strip() and "Name" not in g]
            info["GPU"] = ", ".join(gpus) if gpus else "Unknown"
        except Exception:
            info["GPU"] = "Unknown"
        # PSU info (limited support)
        try:
            psu_out = subprocess.check_output(
                'powershell "Get-WmiObject Win32_PowerSupply | Select-Object Name,Manufacturer"',
                shell=True, text=True
            )
            psu_lines = [l.strip() for l in psu_out.splitlines() if l.strip()]
            info["PSU"] = "; ".join(psu_lines[2:]) if len(psu_lines) > 2 else "Unknown / No telemetry"
        except Exception:
            info["PSU"] = "Unknown / No telemetry"
        # Uptime
        info["Uptime"] = f"{round(time.time() - psutil.boot_time())/3600:.1f} h"
    except Exception as e:
        p(f"[red]❌ sysinfo failed:[/red] {e}")
        return

    text = "\n".join(f"{k}: {v}" for k, v in info.items())
    if save_path:
        Path(save_path).write_text(text, encoding="utf-8")
        p(f"[green]Saved system info →[/green] {save_path}")
    else:
        p(Panel(text, title="🧠 System Info", border_style="cyan") if RICH else text)

        
# ---------- Info / Find / Search ----------
def op_info(path):
    pth = resolve(path)
    if not pth.exists():
        p(f"[red]❌ Not found:[/red] {pth}")
        return
    typ = "dir" if pth.is_dir() else "file"
    size = pth.stat().st_size if pth.is_file() else sum(f.stat().st_size for f in pth.rglob('*') if f.is_file())
    mtime = datetime.datetime.fromtimestamp(pth.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    p(f"[cyan]ℹ️ Info:[/cyan] {pth}\n  Type: {typ}\n  Size: {size:,} bytes\n  Modified: {mtime}")

def op_recent(path=None):
    base = resolve(path or ".")
    items = sorted(base.rglob("*"), key=lambda f: f.stat().st_mtime, reverse=True)[:10]
    p(f"[cyan]🕓 Recent in {base}:[/cyan]")
    for f in items:
        t = datetime.datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        p(f"  {t}  {f}")

def op_biggest(path=None):
    base = resolve(path or ".")
    files = sorted([f for f in base.rglob("*") if f.is_file()], key=lambda f: f.stat().st_size, reverse=True)[:10]
    p(f"[cyan]📦 Largest files in {base}:[/cyan]")
    for f in files:
        p(f"  {f.stat().st_size/1024/1024:6.1f} MB  {f}")

def op_find_name(name):
    base = Path.cwd()
    results = [str(fp) for fp in base.rglob("*") if name.lower() in fp.name.lower()]
    if results:
        p(f"[cyan]🔎 Found {len(results)} match(es):[/cyan]")
        for r in results[:20]:
            p(f"  {r}")
    else:
        p(f"[yellow]No matches for '{name}'.[/yellow]")


def op_find_ext(ext):
    base = Path.cwd()
    results = [str(fp) for fp in base.rglob(f"*{ext}")]
    if results:
        p(f"[cyan]🔎 Files with {ext}:[/cyan]")
        for r in results[:20]:
            p(f"  {r}")
    else:
        p(f"[yellow]No *{ext} files found.[/yellow]")


def op_search_text(term):
    import pathlib
    base = resolve(".")  # respect CMC's virtual directory
    matches = []

    for fp in base.rglob("*"):
        if fp.is_file():
            try:
                txt = fp.read_text(errors="ignore")
                if term.lower() in txt.lower():
                    matches.append(str(fp))
                    if len(matches) >= 20:
                        break
            except Exception:
                continue

    if matches:
        p(f"[cyan]🧠 Found '{term}' in {len(matches)} file(s):[/cyan]")
        for m in matches:
            p(f"  {m}")
    else:
        p(f"[yellow]No text matches for '{term}'.[/yellow]")






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
        
        
# ---------- Timer / Reminder ----------
def op_timer(delay, action=None):
    """
    Start a countdown timer (seconds). When done, prints a message or runs a command.
    Example:
      timer 10 "Done!"
      timer 60 run macro run publish_public
    """
    import threading

    def _trigger():
        if not action:
            p(f"[green bold]✅ Timer finished ({delay}s).[/green bold]")
            return

        text = action.strip()
        low = text.lower()

        if low.startswith("run ") or low.startswith("macro "):
            # Safely run macro/command: force Batch Mode ON so Y/N prompts don’t hang
            p(f"[cyan]⏰ Timer triggered:[/cyan] {text}")
            prev_batch = STATE.get("batch", False)
            STATE["batch"] = True
            try:
                handle_command(text)
            finally:
                STATE["batch"] = prev_batch
        else:
            # Plain text message
            p(Panel(f"⏰ {action}", title="Timer Finished", border_style="green"))

    try:
        delay = int(delay)
        if delay <= 0:
            p("[red]Timer delay must be positive.[/red]")
            return
    except Exception:
        p("[red]Invalid timer delay.[/red]")
        return

    try:
        t = threading.Timer(delay, _trigger)
        t.daemon = True
        t.start()
        p(f"[cyan]⏳ Timer set for {delay} s.[/cyan]")
    except Exception as e:
        p(f"[red]❌ Timer error:[/red] {e}")







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


# ---------- Auto-detect installed Java versions ----------
def detect_java_versions():
    """Scan registry and common folders for Java installations."""
    detected = {}

    try:
        import winreg
        reg_paths = [
            r"SOFTWARE\\Eclipse Adoptium",
            r"SOFTWARE\\JavaSoft\\Java Development Kit",
            r"SOFTWARE\\JavaSoft\\JDK",
            r"SOFTWARE\\JavaSoft\\Java Runtime Environment",
        ]
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for path in reg_paths:
                try:
                    with winreg.OpenKey(root, path) as key:
                        i = 0
                        while True:
                            try:
                                sub = winreg.EnumKey(key, i)
                                with winreg.OpenKey(key, sub) as subkey:
                                    try:
                                        home, _ = winreg.QueryValueEx(subkey, "JavaHome")
                                        if Path(home).exists():
                                            detected[sub] = home
                                    except FileNotFoundError:
                                        pass
                            except OSError:
                                break
                            i += 1
                except FileNotFoundError:
                    continue
    except Exception:
        pass

    # Folder scan fallback
    search_roots = [
        Path("C:/Program Files/Eclipse Adoptium"),
        Path("C:/Program Files/Java"),
        Path("C:/Program Files (x86)/Java"),
    ]
    for root in search_roots:
        if root.exists():
            for sub in root.iterdir():
                if sub.is_dir() and ("jdk" in sub.name.lower() or "jre" in sub.name.lower()):
                    detected[sub.name] = str(sub)

    return detected

JAVA_VERSIONS = detect_java_versions()


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
    


# 🚨 Keep these two exactly at column 0 (no spaces/tabs before them)
MACROS = macros_load()
load_aliases()

def expand_vars(s: str) -> str:
    today = datetime.date.today().isoformat()
    now = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    home = str(Path.home())
    return (
        s.replace("%DATE%", today)
         .replace("%NOW%", now)
         .replace("%HOME%", home)
    )

def macro_add(name: str, text: str):
    name = name.strip()
    if not name:
        p("[red]Macro name required.[/red]"); return
    if not text.strip():
        p("[red]Macro command text required.[/red]"); return
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

def handle_command(s: str):

    # hard-reset any broken global Path
    import pathlib, builtins
    builtins.Path = pathlib.Path
    globals()["Path"] = pathlib.Path

    # --- Runtime Path fix ---
    import pathlib
    globals()["Path"] = pathlib.Path

    import subprocess  # ✅ keep 4-space indentation, same as others

    s = s.strip()
    if not s:
        return

    # Skip comment / empty lines
    if not s.strip() or s.strip().startswith("#"):
        return

        
        
            # ---------- CMD passthrough (inline) ----------
    m = re.match(r"^cmd\s+(.+)$", s, re.I)
    if m:
        cmd_line = m.group(1)
        if STATE.get("dry_run"):
            p(f"[yellow]DRY-RUN:[/yellow] would run CMD → {cmd_line}")
            return
        try:
            import subprocess
            result = subprocess.run(cmd_line, shell=True, text=True, capture_output=True)
            if result.stdout:
                p(result.stdout.strip())
            if result.stderr:
                p(f"[red]{result.stderr.strip()}[/red]")
        except Exception as e:
            p(f"[red]❌ CMD command failed:[/red] {e}")
        return






        # ---------- Alias expansion ----------
    parts = s.split(maxsplit=1)
    if parts and parts[0] in ALIASES:
        alias_cmd = ALIASES[parts[0]]
        rest = parts[1] if len(parts) > 1 else ""
        # Combine alias expansion + remaining args
        s = f"{alias_cmd} {rest}".strip()
        p(f"[dim]↳ alias →[/dim] {s}")
        
            # ---------- Self test ----------
    if s.lower() == "selftest commands":
        try:
            import inspect, re as _re
            defined_ops = sorted([n for n, obj in globals().items()
                                  if n.startswith("op_") and callable(obj)])
            # Rough scan of this function's source for regex routes
            src = inspect.getsource(handle_command)
            routes = sorted(set(m.group(1).strip()
                                for m in _re.finditer(r'^\s*m\s*=\s*re\.match\(\s*r"(\^.+?)"', src, _re.M)))
            p("[cyan]Defined op_* functions:[/cyan]")
            for n in defined_ops: p(f"  {n}")
            p("\n[cyan]Regex routes in handle_command:[/cyan]")
            for r in routes: p(f"  {r}")
        except Exception as e:
            p(f"[red]Selftest failed:[/red] {e}")
        return



    # Fix for broken multi-line commands (when a line ends with "to")
    if s.lower().endswith("to"):
        try:
            nxt = input("... ")
            s = s + " " + nxt.strip()
        except EOFError:
            pass

    # Normalize once
    low = s.lower()
    

    # ---------- Timer command ----------
    m = re.match(r"^timer\s+(\d+)(?:\s+(.+))?$", s, re.I)
    if m:
        op_timer(m.group(1), m.group(2))
        return



    # ---------- Utility automation commands ----------
    m = re.match(r"^sleep\s+(\d+)$", s, re.I)
    if m:
        secs = int(m.group(1))
        time.sleep(secs)
        p(f"😴 Slept for {secs} seconds")
        return

    m = re.match(r'^sendkeys\s+"(.+)"$', s, re.I)
    if m:
        try:
            import pyautogui
            keys = m.group(1)
            if "{ENTER}" in keys.upper():
                parts = re.split(r"\{ENTER\}", keys, flags=re.I)
                for i, part in enumerate(parts):
                    if part.strip():
                        pyautogui.typewrite(part.strip())
                    if i < len(parts) - 1:
                        pyautogui.press("enter")
                        time.sleep(0.2)
            else:
                pyautogui.typewrite(keys)
            p(f"⌨️ Sent keys: {keys}")
        except Exception as e:
            p(f"[red]❌ Sendkeys failed:[/red] {e}")
        return

    # --- Universal run command (supports optional 'in <path>') ---
    m = re.match(r"^run\s+'(.+?)'\s*(?:in\s+'([^']+)')?$", s, re.I)
    if m:
        import pathlib
        full_cmd = m.group(1).strip()
        workdir = pathlib.Path(m.group(2)).expanduser() if m.group(2) else None
        try:
            cwd = str(workdir) if workdir else None
            subprocess.Popen(full_cmd, cwd=cwd, shell=True)
            p(f"🚀 Launched: {full_cmd}" + (f" (cwd={cwd})" if cwd else ""))
        except Exception as e:
            p(f"[red]❌ Failed to run:[/red] {e}")
        return






    # ---------- Control ----------
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
            # ---------- Echo (for macros and inline output) ----------
    m = re.match(r"^echo\s+['\"]?(.+?)['\"]?$", s, re.I)
    if m:
        p(m.group(1))
        return

    if low == "exit":
        sys.exit(0)

    # Simple echo for macros
    m = re.match(r'^echo\s+["“](.+?)["”]$', s, re.I)
    if m:
        p(m.group(1)); return

    # ---------- Git (/git...) ----------
    if low.startswith("/git"):
        if handle_git_commands(s, low):
            return

    # ---------- Alias Commands ----------
    m = re.match(r"^alias\s+add\s+([A-Za-z0-9_\-]+)\s+(.+)$", s, re.I)
    if m:
        name = m.group(1)
        value = m.group(2)
        ALIASES[name] = value
        save_aliases()
        p(f"[cyan]Alias added:[/cyan] {name} → {value}")
        return

    m = re.match(r"^alias\s+delete\s+([A-Za-z0-9_\-]+)$", s, re.I)
    if m:
        name = m.group(1)
        if name in ALIASES:
            del ALIASES[name]
            save_aliases()
            p(f"[yellow]Alias removed:[/yellow] {name}")
        else:
            p(f"[red]Alias not found:[/red] {name}")
        return

    if re.match(r"^alias\s+list$", s, re.I):
        if not ALIASES:
            p("[dim]No aliases defined.[/dim]")
        else:
            for k, v in ALIASES.items():
                p(f"[cyan]{k}[/cyan] → {v}")
        return
        
            # ---------- Java management ----------
    # Fallback helpers in case _apply_java_env / save_java_cfg aren't defined in this build
    def _apply_java_env_local(home_path: str):
        try:
            _apply_java_env(home_path)  # existing helper (if present in your build)
        except NameError:
            # Minimal local apply for this process only
            os.environ["JAVA_HOME"] = home_path
            binp = str(Path(home_path) / "bin")
            if binp not in os.environ.get("PATH", ""):
                os.environ["PATH"] = os.environ.get("PATH", "") + ";" + binp

    def _save_java_cfg_local(ver: str, home_path: str):
        try:
            save_java_cfg(ver, home_path)  # existing helper (if present)
        except NameError:
            pass  # no-op if not present

  

    if low == "java list":
        if not JAVA_VERSIONS:
            p("[yellow]No JAVA_VERSIONS configured in this build.[/yellow]")
        else:
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
            # Try both user and system registry locations
            new_home = None
            for reg_cmd in [
                'reg query "HKCU\\Environment" /v JAVA_HOME',
                'reg query "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Environment" /v JAVA_HOME'
            ]:
                try:
                    out = subprocess.check_output(
                        reg_cmd, shell=True, text=True, stderr=subprocess.DEVNULL
                    )
                    m = re.search(r"JAVA_HOME\s+REG_SZ\s+(.+)", out)
                    if m:
                        new_home = m.group(1).strip()
                        break
                except subprocess.CalledProcessError:
                    continue

            if new_home and Path(new_home).exists():
                _apply_java_env_local(new_home)
                STATE["java_version"] = Path(new_home).name
                _save_java_cfg_local(STATE["java_version"], new_home)
                p(f"🔄 Reloaded Java from registry: {new_home}")
                p(f"✅ Now active: {STATE['java_version']}")
            else:
                p("[yellow]⚠️ No JAVA_HOME found in registry (user or system).[/yellow]")
        except Exception as e:
            p(f"[red]Reload failed:[/red] {e}")
        return


         # ---------- Improved Java change ----------
    m = re.match(r"^java\s+change\s+(.+)$", s, re.I)
    if m:
        arg = m.group(1).strip().strip('"').strip("'")
        target_path = None
        chosen_key = None

        # 1. Try direct key match (version or name)
        if arg in JAVA_VERSIONS:
            target_path = JAVA_VERSIONS[arg]
            chosen_key = arg
        else:
            # 2. Try partial match (e.g. "17" matches "jdk-17.0.16.8-hotspot")
            for k, v in JAVA_VERSIONS.items():
                if arg in k or arg in v:
                    target_path = v
                    chosen_key = k
                    break

        # 3. If still not found, maybe it's a full path
        if not target_path and Path(arg).exists():
            target_path = arg
            chosen_key = Path(arg).name

        if not target_path or not Path(target_path).exists():
            p(f"[red]Java version or path not found:[/red] {arg}")
            return

        # Apply to current process
        os.environ["JAVA_HOME"] = target_path
        bin_path = str(Path(target_path) / "bin")
        if bin_path not in os.environ["PATH"]:
            os.environ["PATH"] += f";{bin_path}"
        STATE["java_version"] = chosen_key or arg
        _save_java_cfg_local(STATE["java_version"], target_path)


        # Apply system-wide via setx
        try:
            subprocess.run(["setx", "JAVA_HOME", target_path],
                           shell=True, check=True, text=True, capture_output=True)
            subprocess.run(["setx", "PATH", f"%PATH%;{bin_path}"],
                           shell=True, check=True, text=True, capture_output=True)
            p(f"✅ Java set to: {chosen_key or target_path}")
            p("⚙️ You can now run 'java reload' in CMC to refresh without reopening.")
        except Exception as e:
            p(f"[yellow]Setx warning:[/yellow] {e}")
        return



        # Apply to current process
        _apply_java_env_local(home)
        STATE["java_version"] = ver
        _save_java_cfg_local(ver, home)

        # Apply system-wide (setx)
        try:
            subprocess.run(["setx", "JAVA_HOME", home], shell=True, check=True,
                           text=True, capture_output=True)
            bin_path = str(Path(home) / "bin")
            # Append bin to PATH
            subprocess.run(["setx", "PATH", f"%PATH%;{bin_path}"], shell=True, check=True,
                           text=True, capture_output=True)
            p(f"✅ Java {ver} set system-wide ({home})")
            p("⚠️ Close and reopen terminals/apps to pick up new PATH.")
        except Exception as e:
            p(f"[yellow]Setx warning:[/yellow] {e}")
        return
        
            # ---------- System Info ----------
    m = re.match(r"^sysinfo(?:\s+save\s+'(.+?)')?$", s, re.I)
    if m:
        op_sysinfo(m.group(1))
        return

        
            # ---------- File & Info operations ----------
    # list ['path']
    m = re.match(r"^list(?:\s+'(.+?)')?$", s, re.I)
    if m:
        op_list(m.group(1) if m.group(1) else None); return

    # info 'path'
    m = re.match(r"^info\s+'(.+?)'$", s, re.I)
    if m:
        op_info(m.group(1)); return

    # find 'name'
    m = re.match(r"^find\s+'(.+?)'$", s, re.I)
    if m:
        op_find_name(m.group(1)); return

    # findext '.ext'
    m = re.match(r"^findext\s+'?(\.[A-Za-z0-9]+)'?$", s, re.I)
    if m:
        op_find_ext(m.group(1)); return

    # recent ['path']
    m = re.match(r"^recent(?:\s+'(.+?)')?$", s, re.I)
    if m:
        op_recent(m.group(1) if m.group(1) else None); return

    # biggest ['path']
    m = re.match(r"^biggest(?:\s+'(.+?)')?$", s, re.I)
    if m:
        op_biggest(m.group(1) if m.group(1) else None); return

    # search 'text'
    m = re.match(r"^search\s+'(.+?)'$", s, re.I)
    if m:
        op_search_text(m.group(1)); return

    # create file 'name.txt' in 'C:/path' [with text="..."]
    m = re.match(r"^create\s+file\s+'(.+?)'\s+in\s+'(.+?)'(?:\s+with\s+text=['\"](.+?)['\"])?$", s, re.I)
    if m:
        op_create_file(m.group(1), m.group(2), m.group(3)); return

    # create folder 'Name' in 'C:/path'
    m = re.match(r"^create\s+folder\s+'(.+?)'\s+in\s+'(.+?)'$", s, re.I)
    if m:
        op_create_folder(m.group(1), m.group(2)); return

    # write 'C:/path/file.txt' text='hello'
    m = re.match(r"^write\s+'(.+?)'\s+text=['\"](.+?)['\"]$", s, re.I)
    if m:
        op_write(m.group(1), m.group(2)); return

    # read 'C:/path/file.txt' [head=50]
    m = re.match(r"^read\s+'(.+?)'(?:\s+\[head=(\d+)\])?$", s, re.I)
    if m:
        op_read(m.group(1), int(m.group(2)) if m.group(2) else None); return

    # move 'C:/src' to 'C:/dst'
    m = re.match(r"^move\s+'(.+?)'\s+to\s+'(.+?)'$", s, re.I)
    if m:
        op_move(m.group(1), m.group(2)); return

    # copy 'C:/src' to 'C:/dst'
    m = re.match(r"^copy\s+'(.+?)'\s+to\s+'(.+?)'$", s, re.I)
    if m:
        op_copy(m.group(1), m.group(2)); return

    # rename 'C:/old' to 'NewName'
    m = re.match(r"^rename\s+'(.+?)'\s+to\s+'(.+?)'$", s, re.I)
    if m:
        op_rename(m.group(1), m.group(2)); return

    # delete 'C:/path'
    m = re.match(r"^delete\s+'(.+?)'$", s, re.I)
    if m:
        op_delete(m.group(1)); return

    # zip 'C:/path'
    m = re.match(r"^zip\s+'(.+?)'$", s, re.I)
    if m:
        op_zip(m.group(1)); return

    # unzip 'C:/file.zip' to 'C:/dest'
    m = re.match(r"^unzip\s+'(.+?)'\s+to\s+'(.+?)'$", s, re.I)
    if m:
        op_unzip(m.group(1), m.group(2)); return

    # open 'C:/file-or-app'
    m = re.match(r"^open\s+'(.+?)'$", s, re.I)
    if m:
        op_open(m.group(1)); return

    # explore 'C:/path'
    m = re.match(r"^explore\s+'(.+?)'$", s, re.I)
    if m:
        op_explore(m.group(1)); return

    # backup 'C:/src' 'C:/dest'
    m = re.match(r"^backup\s+'(.+?)'\s+'(.+?)'$", s, re.I)
    if m:
        op_backup(m.group(1), m.group(2)); return

    # ---------- Internet ----------
    # open url https://example.com  OR  open url 'https://...'
    m = re.match(r"^open\s+url\s+(?:'([^']+)'|(\S+))$", s, re.I)
    if m:
        url = m.group(1) or m.group(2)
        op_open_url(url); return

    # download 'https://...' to 'C:/Downloads'
    m = re.match(r"^download\s+'(.+?)'\s+to\s+'(.+?)'$", s, re.I)
    if m:
        op_download(m.group(1), m.group(2)); return

    # downloadlist 'C:/urls.txt' to 'C:/Downloads'
    m = re.match(r"^downloadlist\s+'(.+?)'\s+to\s+'(.+?)'$", s, re.I)
    if m:
        op_download_list(m.group(1), m.group(2)); return

    # ---------- Run (already have your improved version; keep if missing) ----------
    # run 'cmd or path' [in 'folder']
    m = re.match(r"^run\s+'(.+?)'\s*(?:in\s+'([^']+)')?$", s, re.I)
    if m:
        full_cmd = m.group(1).strip()
        import pathlib
        workdir = pathlib.Path(m.group(2)).expanduser() if m.group(2) else None
        try:
            cwd = str(workdir) if workdir else None
            subprocess.Popen(full_cmd, cwd=cwd, shell=True)
            p(f"🚀 Launched: {full_cmd}" + (f" (cwd={cwd})" if cwd else ""))
        except Exception as e:
            p(f"[red]❌ Failed to run:[/red] {e}")
        return
        
            # ---------- Navigation ----------
    if low in ("home", "cd home"):
        op_home(); return

    if low == "back":
        op_back(); return

    m = re.match(r"^cd\s+'(.+?)'$", s, re.I)
    if m:
        op_cd(m.group(1)); return

    if low == "pwd":
        op_pwd(); return

    # ---------- Backup ----------
    m = re.match(r"^backup\s+'(.+?)'\s+'(.+?)'$", s, re.I)
    if m:
        op_backup(m.group(1), m.group(2)); return

    # ---------- Log / Undo ----------
    if low == "log":
        op_log(); return

    if low == "undo":
        op_undo(); return




    # ---------- Macros (inline) ----------
    m = re.match(r"^macro\s+add\s+([A-Za-z0-9_\-]+)\s*=\s*(.+)$", s, re.I)
    if m: macro_add(m.group(1), m.group(2)); return
    m = re.match(r"^macro\s+run\s+([A-Za-z0-9_\-]+)$", s, re.I)
    if m: macro_run(m.group(1)); return
    m = re.match(r"^macro\s+delete\s+([A-Za-z0-9_\-]+)$", s, re.I)
    if m: macro_delete(m.group(1)); return
    if re.match(r"^macro\s+list$", s, re.I): macro_list(); return
    if re.match(r"^macro\s+clear$", s, re.I): macro_clear(); return
    
        # ---------- File Operations ----------
    m = re.match(r"^create\s+file\s+'(.+?)'\s+in\s+'(.+?)'(?:\s+with\s+text=['\"](.+?)['\"])?$", s, re.I)
    if m:
        op_create_file(m.group(1), m.group(2), m.group(3))
        return

    m = re.match(r"^create\s+folder\s+'(.+?)'\s+in\s+'(.+?)'$", s, re.I)
    if m:
        op_create_folder(m.group(1), m.group(2))
        return

    m = re.match(r"^write\s+'(.+?)'\s+text=['\"](.+?)['\"]$", s, re.I)
    if m:
        op_write(m.group(1), m.group(2))
        return

    m = re.match(r"^read\s+'(.+?)'(?:\s+\[head=(\d+)\])?$", s, re.I)
    if m:
        op_read(m.group(1), int(m.group(2)) if m.group(2) else None)
        return

    m = re.match(r"^move\s+'(.+?)'\s+to\s+'(.+?)'$", s, re.I)
    if m:
        op_move(m.group(1), m.group(2))
        return

    m = re.match(r"^copy\s+'(.+?)'\s+to\s+'(.+?)'$", s, re.I)
    if m:
        op_copy(m.group(1), m.group(2))
        return

    m = re.match(r"^rename\s+'(.+?)'\s+to\s+'(.+?)'$", s, re.I)
    if m:
        op_rename(m.group(1), m.group(2))
        return

    m = re.match(r"^delete\s+'(.+?)'$", s, re.I)
    if m:
        op_delete(m.group(1))
        return


    # ---------- Navigation ----------
    # (keep your existing navigation / file ops / java / index handlers here...)

    # ---------- Internet ----------
    m = re.match(r"^open\s+url\s+(?:'([^']+)'|(\S+))$", s, re.I)
    if m:
        url = m.group(1) or m.group(2)
        op_open_url(url)
        return

    # ---------- Web search (default browser e.g. Brave) ----------
    m = re.match(r"^search\s+web\s+(.+)$", s, re.I)
    if m:
        q = m.group(1).strip()
        if q:
            url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(q)
            webbrowser.open(url)
            p(f"[cyan]🌐 Opened Google search for:[/cyan] {q}")
        else:
            p("Usage: search web <text>")
        return

    m = re.match(r"^youtube\s+(.+)$", s, re.I)
    if m:
        q = m.group(1).strip()
        if q:
            url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(q)
            webbrowser.open(url)
            p(f"[cyan]🎬 Opened YouTube search for:[/cyan] {q}")
        else:
            p("Usage: youtube <text>")
        return


        
        # ---------- Web search (opens your default browser e.g., Brave) ----------
    m = re.match(r"^search\s+web\s+(.+)$", s, re.I)
    if m:
        q = m.group(1).strip()
        if q:
            url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(q)
            webbrowser.open(url)
            p(f"[cyan]🌐 Opened Google search for:[/cyan] {q}")
        else:
            p("Usage: search web <text>")
        return

    m = re.match(r"^youtube\s+(.+)$", s, re.I)
    if m:
        q = m.group(1).strip()
        if q:
            url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(q)
            webbrowser.open(url)
            p(f"[cyan]🎬 Opened YouTube search for:[/cyan] {q}")
        else:
            p("Usage: youtube <text>")
        return
        
        # ---------- Local Path Index ----------
    # /qfind <terms> [limit]
    m = re.match(r"^/qfind\s+(.+?)(?:\s+(\d+))?$", s, re.I)
    if m:
        terms = m.group(1)
        limit = int(m.group(2)) if m.group(2) else 20
        try:
            from path_index_local import quick_find
            results = quick_find(terms, limit)
            if results:
                p(f"[cyan]Top {len(results)} results for '{terms}':[/cyan]")
                for r in results:
                    p(f"  {r}")
            else:
                p(f"[yellow]No matches found for '{terms}'.[/yellow]")
        except Exception as e:
            p(f"[red]Quick-find error:[/red] {e}")
        return

    # /qcount
    if re.match(r"^/qcount$", s, re.I):
        try:
            from path_index_local import quick_count
            count = quick_count()
            p(f"📁 Indexed paths: {count}")
        except Exception as e:
            p(f"[red]Quick-count error:[/red] {e}")
        return

    # /qbuild [targets...]
    m = re.match(r"^/qbuild(?:\s+(.+))?$", s, re.I)
    if m:
        targets = m.group(1)
        try:
            from path_index_local import quick_build
            quick_build(targets)
        except Exception as e:
            p(f"[red]Quick-build error:[/red] {e}")
        return



    # ---------- CMD passthrough ----------
    # Opens a real Windows Command Prompt session inside the same window.
    # Type 'exit' to return back to CMC after using normal CMD commands.
    if low == "cmd":
        if STATE.get("dry_run"):
            p("[yellow]DRY-RUN:[/yellow] CMD session skipped.")
            return
        if not STATE.get("batch"):
            if not confirm("Open a full CMD session? You can type 'exit' to return to CMC."):
                p("[yellow]Canceled.[/yellow]")
                return
        try:
            p("[cyan]Entering Windows CMD mode — type 'exit' to return to CMC.[/cyan]")
            os.system("cmd")
            p("[cyan]Returned from CMD mode.[/cyan]")
        except Exception as e:
            p(f"[red]❌ CMD session failed:[/red] {e}")
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
"  run 'C:/path/app.exe'              Run any file or command\n"
"  run 'cmd.exe /c start \"\" \"C:/Path/File.bat\"'  Launch batch or shortcut externally\n"
"  run 'C:/path/script.py' in 'C:/folder'   Run with working directory\n\n"
"────────────────────────────────────────────────────────\n\n"
"🌍 INTERNET — Download with 1 GB safety cap\n"
"  download 'https://...' to 'C:/Downloads'\n"
"  downloadlist 'C:/urls.txt' to 'C:/Downloads'\n"
"  open url 'https://example.com'\n"
"  search web <query>          Open Google search in your default browser\n"
"  youtube <query>             Search YouTube in your default browser\n\n"
"────────────────────────────────────────────────────────\n\n"
"🧰 MACROS (persistent) — Save and run command sequences\n"
"  macro add <name> = <commands>\n"
"  macro run <name>\n"
"  macro list\n"
"  macro delete <name>    macro clear\n"
"  Vars available: %DATE%, %NOW%, %HOME%\n\n"
"────────────────────────────────────────────────────────\n\n"
"⚡ ALIASES — Custom command shortcuts (lightweight macros)\n"
"  alias add <name> <command>    Create a shortcut\n"
"  alias list                    Show saved aliases\n"
"  alias delete <name>           Remove a shortcut\n"
"  alias clear                   Delete all aliases\n\n"
"  Examples:\n"
"    alias add g search web\n"
"    alias add yt youtube\n"
"    g python subprocess example\n"
"    yt trackmania drift\n\n"
"────────────────────────────────────────────────────────\n\n"
"⏲️ TIMER & REMINDERS — Run commands or messages after delay\n"
"  timer <seconds> [action]\n"
"      Start a countdown timer (in seconds).\n"
"      When time expires:\n"
"        • If [action] is text, it prints a reminder.\n"
"        • If [action] starts with 'run' or 'macro', that command is executed automatically.\n\n"
"  Examples:\n"
"      timer 10 \"Take a break!\"\n"
"      timer 5 run macro run publish_public\n"
"      timer 60 macro run backup_journey\n\n"
"────────────────────────────────────────────────────────\n\n"
"🪟 CMD PASSTHROUGH — Use real Windows commands inside CMC\n"
"  cmd                         Open full Windows Command Prompt (type 'exit' to return)\n"
"  cmd <command>               Run a Windows CMD command directly\n\n"
"  Examples:\n"
"      cmd dir\n"
"      cmd ipconfig /all\n"
"      cmd sfc /scannow\n\n"
"────────────────────────────────────────────────────────\n\n"
"⛭ CONTROL — Toggles & utilities\n"
"  batch on | batch off        Auto-confirm prompts (skip Y/N)\n"
"  dry-run on | dry-run off    Preview actions without executing\n"
"  ssl on | ssl off            Toggle HTTPS certificate verification\n"
"  status                     Show current Computer Main Centre state (Batch / SSL / Dry-Run / Java)\n"
"  log                        Show operation history\n"
"  undo                       Undo last reversible action\n"
"  sleep <seconds>             Pause execution in macros (e.g., sleep 3)\n"
"  sendkeys \"<text>{ENTER}\"     Send keyboard input to the active window\n"
"  help                       Display this help menu\n"
"  exit                       Close Computer Main Centre\n\n"
"────────────────────────────────────────────────────────\n\n"
"☕ JAVA — Manage system-wide Java environment\n"
"  java list                   Auto-detect and show all installed Java versions\n"
"  java version                Show currently active Java version and JAVA_HOME\n"
"  java change <version|name|path>  Switch to a specific JDK/JRE (supports full path)\n"
"  java reload                 Reload JAVA_HOME and PATH from the Windows registry\n\n"
"  Examples:\n"
"    java change 17\n"
"    java change jdk-21.0.8.9-hotspot\n"
"    java change 'C:/Program Files/Java/jdk-17'\n"
"    java reload\n"
"────────────────────────────────────────────────────────\n\n"
"🔎 LOCAL PATH INDEX (no server) — Instant search of your drives\n"
"  /qfind <terms> [limit]      Multi-word AND search (default limit 20)\n"
"  /qcount                     Show total indexed paths\n"
"  /qbuild [targets...]        Rebuild/refresh index (e.g. %USERPROFILE% C E F)\n\n"
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
"  backup '%USERPROFILE%/Downloads' to 'C:/Backups'\n\n"
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
    """
    Splits chained commands separated by semicolons (;)
    but keeps whole lines for 'macro add' and 'timer' commands.
    """
    parts = []
    buf = []
    q = None
    in_macro_add = False
    i = 0

    line = line.rstrip()
    if not line:
        return []

    # if it's a timer command, never split it
    if line.lower().startswith("timer "):
        return [line]

    while i < len(line):
        ch = line[i]

        if q:
            # we're inside a quoted string
            if ch == q:
                q = None
            buf.append(ch)
        else:
            # not in quotes
            if not in_macro_add:
                temp = "".join(buf).lstrip().lower()
                if temp.startswith("macro add"):
                    in_macro_add = True

            if ch in ("'", '"'):
                q = ch
                buf.append(ch)
            elif ch == ";" and not in_macro_add:
                part = "".join(buf).strip()
                if part:
                    parts.append(part)
                buf = []
            else:
                buf.append(ch)

        i += 1

    # append any remaining buffer once
    final = "".join(buf).strip()
    if final:
        parts.append(final)

    # DEBUG optional
    # print("[DEBUG split_commands]", parts)
    return parts



import shlex


# ---------- Command Autocompletion ----------

def complete_path(text, state):
    """Auto-complete file and folder paths when typing quoted paths."""
    if text.startswith(("'", '"')):
        quote = text[0]
        text = text[1:]
    else:
        quote = ''

    pattern = text + '*' if text else '*'
    matches = glob.glob(pattern)
    results = [f"{quote}{m.replace('\\', '/')}" for m in matches]

    # Append a trailing slash for directories
    results = [r + ('/' if os.path.isdir(r.strip("'\"")) else '') for r in results]
    return results[state] if state < len(results) else None


def complete_command(text, state):
    """Autocomplete for commands, macros, git commands, and paths."""
    cmds = [
        "pwd", "cd", "back", "home", "list", "info", "find", "findext",
        "recent", "biggest", "search", "create file", "create folder",
        "write", "read", "move", "copy", "rename", "delete", "zip",
        "unzip", "open", "explore", "backup", "run", "download",
        "downloadlist", "open url", "batch on", "batch off", "dry-run on",
        "dry-run off", "ssl on", "ssl off", "status", "log", "undo",
        "macro add", "macro run", "macro list", "macro delete", "macro clear",
        "/gitsetup", "/gitlink", "/gitupdate", "/gitpull", "/gitstatus",
        "/gitlog", "/gitbranch", "/gitignore add", "/gitclean", "/gitdoctor",
        "/gitfix", "/gitlfs setup", "/qfind", "/qcount", "/qbuild",
        "java list", "java version", "java change", "java reload",
        "sleep", "sendkeys", "help", "exit"
    ]
    cmds += list(MACROS.keys())  # include macro names

    if text.startswith(("'", '"')):
        return complete_path(text, state)

    results = [c for c in cmds if c.lower().startswith(text.lower())]
    return results[state] if state < len(results) else None


def setup_autocomplete():
    if readline is None:
        print("(Autocomplete disabled — readline not available)")
        return

    readline.set_completer_delims(' \t\n')
    readline.set_completer(complete_command)
    readline.parse_and_bind("tab: complete")

    # 🪄 Patch TAB key to trigger inline insert behavior
    # This works by overriding readline's key bindings
    try:
        readline.parse_and_bind('"\t": complete')  # standard bind
        # Replace readline's default completer handler
        readline.set_completion_display_matches_hook(
            lambda substitution, matches, longest_match_length:
                complete_and_insert()
        )
    except Exception:
        pass

    
# ---------- Inline completion helper (Windows-friendly) ----------

def complete_and_insert():
    """Force inline completion instead of just listing matches."""
    if readline is None:
        return
    buffer = readline.get_line_buffer()
    cursor = readline.get_endidx()
    matches = []
    state = 0
    while True:
        res = complete_command(buffer, state)
        if res is None:
            break
        matches.append(res)
        state += 1
    if len(matches) == 1:
        # single match → auto-insert remainder
        match = matches[0]
        remainder = match[len(buffer):]
        if remainder:
            sys.stdout.write(remainder)
            sys.stdout.flush()
            readline.insert_text(remainder)
    elif len(matches) > 1:
        # multiple matches → show them like bash
        print()
        print("  ".join(matches))
        readline.redisplay()




# ---------- Advanced input with live autocomplete ----------
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.styles import Style

# ---------- Dynamic Autocomplete Builder ----------
def build_completer():
    """
    Dynamically extract all command names from handle_command()
    regex routes + macros + aliases for live autocomplete.
    """
    import inspect, re

    cmds = []
    try:
        # --- 1. Scan handle_command source for regex routes ---
        src = inspect.getsource(handle_command)
        found = re.findall(r'\^([A-Za-z0-9/_\-]+)', src)
        cmds = sorted(set(found))
    except Exception:
        pass

    # --- 2. Add static helper words & toggles ---
    base_cmds = [
        "help", "exit", "status",
        "batch on", "batch off",
        "dry-run on", "dry-run off",
        "ssl on", "ssl off",
        "sleep", "sendkeys"
    ]
    cmds += base_cmds

    # --- 3. Include all macros and aliases dynamically ---
    try:
        # Always reload latest macros from disk to include old ones
        macro_data = macros_load()
        cmds += list(macro_data.keys())
    except Exception:
        pass

    try:
        cmds += list(ALIASES.keys())
    except Exception:
        pass

    # --- 4. Clean duplicates & sort ---
    cmds = sorted(set(cmds), key=str.lower)

    # --- 5. Return the prompt_toolkit completer ---
    return WordCompleter(cmds, ignore_case=True)



# create a prompt session
session = PromptSession()

# 🎨 CMC cyan theme style
style = Style.from_dict({
        # Prompt label text
    "prompt": "#00ffff bold",

    # Regular suggestions (cyan text, transparent dark background)
    "completion-menu.completion": "bg:#1a1a1a #00ffff",

    # The currently highlighted / selected completion
    "completion-menu.completion.current": "bg:#0033cc #ffffff",

    # Scrollbar (dark blue track + blue handle)
    "scrollbar.background": "bg:#0d0d0d",
    "scrollbar.button": "bg:#0033cc",
})  # ✅ <-- closing both parentheses




def main():
    global CWD
    show_header()

    # Ensure macros are always loaded fresh from disk
    global MACROS
    MACROS = macros_load()

    completer = build_completer()

    while True:
        try:
            line = session.prompt(
                f"CMC>{CWD}> ",
                completer=completer,
                complete_while_typing=True,
                style=style
            )
        except (EOFError, KeyboardInterrupt):
            print()
            break

        for part in split_commands(line):
            # Prevent timer from splitting its message argument
            if part.lower().startswith("timer "):
                handle_command(line)   # run the whole thing once
                break

            try:
                handle_command(part)
            except SystemExit:
                raise
            except Exception as e:
                p(f"[red]❌ Error:[/red] {e}" if RICH else f"Error: {e}")




if __name__ == "__main__":
    main()


# // test: autopublish propagation checkssssssssssssss
