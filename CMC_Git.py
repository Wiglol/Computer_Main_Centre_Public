import base64
import datetime
import json
import re
import shutil
import subprocess
import shlex
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Tuple, Union, List

# ------------------------------------------------------------
# CMC_Git.py — Git + GitHub module for Computer Main Centre
#
# Easy commands:
#   git upload
#   git update [owner/repo|url|repoName] ["commit msg"] [--add <path>]
#   git link <owner/repo|url>
#   git open
#   git download <owner/repo|url>
#   git repo list [all|mine]
#   git repo delete <owner/repo|repoName>
#   git doctor
#
# NEW (self-healing):
#   git force upload
#   git force update [owner/repo|url|repoName] ["commit msg"] [--add <path>]
#   git debug upload
#   git debug update [owner/repo|url|repoName] ["commit msg"] [--add <path>]
#
# Pass-through:
#   Any other "git ..." is forwarded to real git.
#
# Safety:
# - Never print tokens
# - Never embed token in URL
# - Uses temporary http.extraheader for authenticated git over HTTPS
# ------------------------------------------------------------

PFunc = Callable[[str], None]

GIT_CFG = Path.home() / ".ai_helper" / "github.json"
GIT_CFG.parent.mkdir(parents=True, exist_ok=True)

AUTH_ERR_MARKERS = (
    "authentication failed",
    "fatal: could not read username",
    "fatal: could not read password",
    "http 401",
    "http 403",
    "permission denied",
    "repository not found",
    "access denied",
)

# Default ignore patterns for CMC Git (general-purpose + safe defaults)
# NOTE: We intentionally do NOT ignore *.exe / *.dll / *.mp4 / *.zip etc.
# People often want to publish binaries/media/releases.
DEFAULT_GITIGNORE_PATTERNS = [
    # --- CMC local/cache ---
    "paths.db",
    "centre_index*.json",
    ".ai_helper/",
    "CMC_GIT_DEBUG_*.txt",

    # --- Secrets / local env (safe default) ---
    ".env",
    ".env.*",
    "!.env.example",
    "*.key",
    "*.pem",
    "*.pfx",
    "*.p12",
    "*.crt",
    "*.cer",
    "secrets.json",
    "credentials.json",

    # --- Logs / temp ---
    "*.log",
    "*.tmp",
    "*.temp",
    "*.bak",
    "*.swp",
    "*.swo",
    "*.old",
    "*.orig",
    "*.cache",

    # --- Databases / local state ---
    "*.db",
    "*.sqlite",
    "*.sqlite3",

    # --- OS clutter ---
    "Thumbs.db",
    "Thumbs.db:encryptable",
    "Desktop.ini",
    "$RECYCLE.BIN/",
    ".DS_Store",
    ".AppleDouble",
    ".LSOverride",

    # --- Python ---
    "__pycache__/",
    "*.py[cod]",
    "*$py.class",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    ".pytype/",
    ".coverage",
    "coverage.xml",
    "htmlcov/",

    # --- Virtual envs ---
    ".venv/",
    "venv/",
    "ENV/",
    "env/",
    ".python-version",

    # --- Python packaging ---
    "build/",
    "dist/",
    "*.egg-info/",
    ".eggs/",
    "wheels/",
    "*.whl",

    # --- Jupyter ---
    ".ipynb_checkpoints/",

    # --- IDEs/editors ---
    ".vscode/",
    ".idea/",
    "*.iml",
    "*.sublime-project",
    "*.sublime-workspace",

    # --- Node / frontend ---
    "node_modules/",
    "npm-debug.log*",
    "yarn-debug.log*",
    "yarn-error.log*",
    "pnpm-debug.log*",
    ".parcel-cache/",
    ".next/",
    "out/",
]

@dataclass
class GitIdentity:
    token: str
    username: str


# ---------------------------
# Config
# ---------------------------

def _cfg_load() -> dict:
    try:
        if GIT_CFG.exists():
            return json.loads(GIT_CFG.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        pass
    return {}

def _cfg_save(data: dict) -> None:
    try:
        GIT_CFG.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass

def _get_saved_token() -> str:
    data = _cfg_load()
    return (data.get("token") or "").strip()

def _set_saved_token(tok: str) -> None:
    data = _cfg_load()
    data["token"] = (tok or "").strip()
    _cfg_save(data)

def _remember_repo(folder_root: Path, owner: str, repo: str, remote: str) -> None:
    data = _cfg_load()
    repos = data.get("repos", {})
    if not isinstance(repos, dict):
        repos = {}
    repos[str(folder_root)] = {"owner": owner, "name": repo, "remote": remote}
    data["repos"] = repos
    _cfg_save(data)

def _remembered_repo(folder_root: Path) -> Optional[dict]:
    data = _cfg_load()
    repos = data.get("repos", {})
    if not isinstance(repos, dict):
        return None
    info = repos.get(str(folder_root))
    return info if isinstance(info, dict) else None


# ---------------------------
# Parsing / prompts
# ---------------------------

def _tokens(raw: str) -> List[str]:
    try:
        return shlex.split(raw, posix=False)
    except Exception:
        return raw.strip().split()

def _prompt(msg: str, default: Optional[str] = None) -> str:
    if default is not None and default != "":
        raw = input(f"{msg} [{default}]: ").strip()
        return raw or default
    return input(f"{msg}: ").strip()

def _prompt_public(default_public: bool = True) -> bool:
    d = "y" if default_public else "n"
    raw = input(f"Public repository? (y/n) [{d}]: ").strip().lower()
    if not raw:
        return default_public
    if raw.startswith("y"):
        return True
    if raw.startswith("n") or raw.startswith("s"):
        return False
    return default_public

def _sanitize_repo_name(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name)
    name = name.strip("-.")
    return name or "repo"

def _parse_repo_spec(spec: str) -> Optional[Tuple[str, str]]:
    """
    Accepts:
      - owner/repo
      - https://github.com/owner/repo
      - https://github.com/owner/repo.git
      - git@github.com:owner/repo.git
    Returns (owner, repo) or None.
    """
    s = (spec or "").strip().strip('"').strip("'")
    if not s:
        return None

    if "github.com" in s.lower():
        m = re.search(r"github\.com[/:]([^/]+)/([^/]+?)(?:\.git)?/?$", s, re.I)
        if m:
            owner = m.group(1).strip()
            repo = m.group(2).strip()
            repo = repo[:-4] if repo.lower().endswith(".git") else repo
            return owner, repo

    if "/" in s:
        owner, repo = s.split("/", 1)
        owner = owner.strip()
        repo = repo.strip()
        repo = repo[:-4] if repo.lower().endswith(".git") else repo
        if owner and repo:
            return owner, repo

    return None

def _is_github_remote(url: str) -> bool:
    u = (url or "").lower()
    return "github.com" in u

def _remote_web_url(remote: str) -> Optional[str]:
    if not remote:
        return None

    # strip embedded auth if present
    if "@" in remote and remote.startswith("https://"):
        remote = "https://" + remote.split("@", 1)[1]

    spec = _parse_repo_spec(remote)
    if spec:
        owner, repo = spec
        return f"https://github.com/{owner}/{repo}"
    return None

def _safe_remote_str(remote: str) -> str:
    r = (remote or "").strip()
    if r.startswith("https://") and "@" in r:
        return "https://" + r.split("@", 1)[1]
    return r

def _looks_like_placeholder_remote(remote: str) -> bool:
    r = (remote or "")
    return "<you>" in r or "%YOU%" in r or "YOURNAME" in r.upper()


# ---------------------------
# Git helpers
# ---------------------------

def _git_installed() -> bool:
    return bool(shutil.which("git"))

def _looks_like_auth_error(out: str) -> bool:
    o = (out or "").lower()
    return any(m in o for m in AUTH_ERR_MARKERS)

def _git_run(args: List[str], cwd: Union[str, Path], identity: Optional[GitIdentity] = None) -> Tuple[int, str]:
    """
    Run git.
    If identity is provided, use a non-persistent GitHub Basic auth header.
    """
    if not _git_installed():
        return 127, "git not found in PATH"

    cmd = ["git"]
    if identity:
        b64 = base64.b64encode(f"{identity.username}:{identity.token}".encode("utf-8")).decode("ascii")
        cmd += ["-c", f"http.extraheader=AUTHORIZATION: basic {b64}"]

    cmd += args

    try:
        r = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True)
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        combined = (out + ("\n" + err if err else "")).strip()
        return r.returncode, combined or "(done)"
    except Exception as e:
        return 1, str(e)

def _resolve_repo_root(start: Path) -> Path:
    rc, out = _git_run(["rev-parse", "--show-toplevel"], cwd=start)
    if rc == 0 and out and "fatal" not in out.lower():
        pth = Path(out.strip())
        if pth.exists():
            return pth
    return start

def _ensure_repo_initialized(root: Path) -> None:
    if not (root / ".git").exists():
        _git_run(["init"], cwd=root)

def _get_origin_remote(root: Path) -> str:
    rc, out = _git_run(["remote", "get-url", "origin"], cwd=root)
    if rc == 0:
        return out.strip()
    return ""

def _set_origin_remote(root: Path, remote_url: str) -> None:
    rc, _ = _git_run(["remote", "get-url", "origin"], cwd=root)
    if rc == 0:
        _git_run(["remote", "set-url", "origin", remote_url], cwd=root)
    else:
        _git_run(["remote", "add", "origin", remote_url], cwd=root)

def _has_commits(root: Path) -> bool:
    rc, _ = _git_run(["rev-parse", "--verify", "HEAD"], cwd=root)
    return rc == 0

def _status_porcelain(root: Path) -> str:
    _, out = _git_run(["status", "--porcelain"], cwd=root)
    return out.strip()

def _gitignore_add(root: Path, patterns: List[str]) -> None:
    gi = root / ".gitignore"

    try:
        existing = gi.read_text(encoding="utf-8", errors="ignore").splitlines() if gi.exists() else []
    except Exception:
        existing = []

    # Keep original lines (including comments), but prevent duplicates for actual rules.
    existing_set = set(line.strip() for line in existing if line.strip() and not line.strip().startswith("#"))

    added = False
    to_append: List[str] = []
    for ptn in patterns:
        rule = (ptn or "").strip()
        if not rule:
            continue
        if rule not in existing_set:
            to_append.append(rule)
            existing_set.add(rule)
            added = True

    if not gi.exists():
        header = [
            "# ============================================================",
            "# .gitignore generated/maintained by CMC",
            "# (safe defaults; binaries/media are NOT ignored by default)",
            "# ============================================================",
            "",
        ]
        gi.write_text("\n".join(header + to_append) + "\n", encoding="utf-8")
        return

    if added:
        # append with a small section marker
        with gi.open("a", encoding="utf-8") as f:
            f.write("\n# --- Added by CMC ---\n")
            for rule in to_append:
                f.write(rule + "\n")


def _warn_big_files(root: Path, limit_mb: int = 100) -> List[str]:
    limit = limit_mb * 1024 * 1024
    big: List[str] = []
    try:
        for fp in root.rglob("*"):
            if ".git" in fp.parts:
                continue
            if fp.is_file() and fp.stat().st_size > limit:
                big.append(str(fp.relative_to(root)))
    except Exception:
        pass
    return big

def _ensure_readme_if_empty(root: Path) -> None:
    if _has_commits(root):
        return

    _git_run(["add", "-A"], cwd=root)
    if _status_porcelain(root):
        return

    readme = root / "README.md"
    if not readme.exists():
        readme.write_text(f"# {root.name}\n", encoding="utf-8")
    _git_run(["add", "README.md"], cwd=root)

def _ensure_branch(root: Path, branch: str) -> Tuple[int, str]:
    """
    Make sure we're on <branch>. Tries a few strategies for max compatibility.
    """
    branch = (branch or "").strip() or "main"

    rc, out = _git_run(["checkout", "-B", branch], cwd=root)
    if rc == 0:
        return rc, out

    rc2, out2 = _git_run(["checkout", "-b", branch], cwd=root)
    if rc2 == 0:
        return rc2, out2

    rc3, out3 = _git_run(["branch", "-M", branch], cwd=root)
    return rc3, out3

def _commit_if_needed(root: Path, msg: str) -> str:
    _git_run(["add", "-A"], cwd=root)
    rc, out = _git_run(["commit", "-m", msg], cwd=root)
    if rc != 0 and "nothing to commit" in out.lower():
        return "ℹ️ Nothing to commit."
    if rc != 0:
        return f"❌ Commit failed:\n{out}"
    return "✅ Committed."

def _commit_only_paths(root: Path, paths: List[str], msg: str) -> str:
    for rawp in paths:
        pth = rawp.strip().strip('"').strip("'")
        if not pth:
            continue

        pp = Path(pth)
        if pp.is_absolute():
            try:
                rel = pp.resolve().relative_to(root.resolve())
                pth = str(rel)
            except Exception:
                return f"❌ Path is not inside repo root:\n{pp}"

        rc, out = _git_run(["add", "--", pth], cwd=root)
        if rc != 0:
            return f"❌ git add failed for {pth}:\n{out}"

    rc, out = _git_run(["commit", "-m", msg], cwd=root)
    if rc != 0 and "nothing to commit" in out.lower():
        return "ℹ️ Nothing to commit."
    if rc != 0:
        return f"❌ Commit failed:\n{out}"
    return "✅ Committed (partial)."

def _push(root: Path, identity: Optional[GitIdentity]) -> Tuple[int, str]:
    remote = _get_origin_remote(root)
    if _looks_like_placeholder_remote(remote):
        return 128, "Origin remote contains placeholder '<you>'. Fix origin to a real repo (git link owner/repo)."

    if identity and remote and _is_github_remote(remote) and remote.startswith("https://"):
        rc, out = _git_run(["push"], cwd=root, identity=identity)
        if rc == 0:
            return rc, out
        if _looks_like_auth_error(out):
            return _git_run(["push"], cwd=root, identity=None)
        return rc, out
    return _git_run(["push"], cwd=root, identity=None)

def _push_branch(root: Path, branch: str, identity: Optional[GitIdentity]) -> Tuple[int, str]:
    remote = _get_origin_remote(root)
    if _looks_like_placeholder_remote(remote):
        return 128, "Origin remote contains placeholder '<you>'. Fix origin to a real repo (git link owner/repo)."

    args = ["push", "--set-upstream", "origin", branch]
    if identity and remote and _is_github_remote(remote) and remote.startswith("https://"):
        rc, out = _git_run(args, cwd=root, identity=identity)
        if rc == 0:
            return rc, out
        if _looks_like_auth_error(out):
            return _git_run(args, cwd=root, identity=None)
        return rc, out
    return _git_run(args, cwd=root, identity=None)

def _pull_rebase(root: Path, branch: str, identity: Optional[GitIdentity]) -> Tuple[int, str]:
    remote = _get_origin_remote(root)
    if _looks_like_placeholder_remote(remote):
        return 128, "Origin remote contains placeholder '<you>'. Fix origin to a real repo (git link owner/repo)."

    args = ["pull", "--rebase", "origin", branch]
    if identity and remote and _is_github_remote(remote) and remote.startswith("https://"):
        rc, out = _git_run(args, cwd=root, identity=identity)
        if rc == 0:
            return rc, out
        if _looks_like_auth_error(out):
            return _git_run(args, cwd=root, identity=None)
        return rc, out
    return _git_run(args, cwd=root, identity=None)

def _push_force_with_lease(root: Path, branch: str, identity: Optional[GitIdentity]) -> Tuple[int, str]:
    remote = _get_origin_remote(root)
    if _looks_like_placeholder_remote(remote):
        return 128, "Origin remote contains placeholder '<you>'. Fix origin to a real repo (git link owner/repo)."

    args = ["push", "--force-with-lease", "origin", branch]
    if identity and remote and _is_github_remote(remote) and remote.startswith("https://"):
        rc, out = _git_run(args, cwd=root, identity=identity)
        if rc == 0:
            return rc, out
        if _looks_like_auth_error(out):
            return _git_run(args, cwd=root, identity=None)
        return rc, out
    return _git_run(args, cwd=root, identity=None)

def _auto_update_message() -> str:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"Update {now}"

def _remote_head_branch(root: Path, identity: Optional[GitIdentity]) -> str:
    remote = _get_origin_remote(root)
    if not remote:
        return ""
    use_ident = identity if (identity and remote.startswith("https://") and _is_github_remote(remote)) else None
    rc, out = _git_run(["remote", "show", "origin"], cwd=root, identity=use_ident)
    if rc != 0:
        return ""
    m = re.search(r"HEAD branch:\s*([A-Za-z0-9._/\-]+)", out)
    if m:
        return m.group(1).strip()
    return ""

def _ensure_git_user_config(root: Path, ident: Optional[GitIdentity]) -> None:
    rc1, name = _git_run(["config", "--get", "user.name"], cwd=root)
    rc2, email = _git_run(["config", "--get", "user.email"], cwd=root)
    need_name = (rc1 != 0) or (not (name or "").strip())
    need_email = (rc2 != 0) or (not (email or "").strip())

    if need_name:
        fallback = ident.username if ident else "CMC"
        _git_run(["config", "user.name", fallback], cwd=root)
    if need_email:
        if ident and ident.username:
            mail = f"{ident.username}@users.noreply.github.com"
        else:
            mail = "cmc@users.noreply.github.com"
        _git_run(["config", "user.email", mail], cwd=root)

def _maybe_remove_index_lock(root: Path) -> Tuple[bool, str]:
    lock = root / ".git" / "index.lock"
    if not lock.exists():
        return False, ""
    try:
        lock.unlink()
        return True, f"Removed index.lock: {lock}"
    except Exception as e:
        return False, f"Failed to remove {lock}: {e}"

def _write_debug_report(root: Path, title: str, content: str) -> Optional[Path]:
    try:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        fp = root / f"CMC_GIT_DEBUG_{ts}.txt"
        fp.write_text(f"{title}\n\n{content}\n", encoding="utf-8", errors="ignore")
        return fp
    except Exception:
        return None


# ---------------------------
# GitHub API
# ---------------------------

def _gh_request(method: str, url: str, token: str, body: Optional[dict] = None) -> Tuple[int, str]:
    import urllib.error
    import urllib.request

    headers = {
        "User-Agent": "CMC-GitAssistant",
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
    }

    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        return e.code, raw
    except Exception as e:
        return 0, str(e)

def _gh_username(token: str) -> Optional[str]:
    code, raw = _gh_request("GET", "https://api.github.com/user", token)
    if code != 200:
        return None
    try:
        return json.loads(raw).get("login")
    except Exception:
        return None

def _gh_create_repo(token: str, name: str, private: bool) -> Tuple[bool, str]:
    code, raw = _gh_request(
        "POST",
        "https://api.github.com/user/repos",
        token,
        body={"name": name, "private": private, "auto_init": False},
    )
    if code in (201, 202):
        return True, "created"
    if code == 422:
        return True, "already-exists"
    return False, raw

def _gh_list_repos(token: str, affiliation: str = "owner,collaborator,organization_member") -> List[dict]:
    repos: List[dict] = []
    page = 1
    while True:
        url = (
            "https://api.github.com/user/repos"
            f"?per_page=100&page={page}"
            f"&affiliation={affiliation}"
            "&visibility=all"
            "&sort=updated"
        )
        code, raw = _gh_request("GET", url, token)
        if code != 200:
            break
        data = json.loads(raw)
        if not data:
            break
        repos.extend(data)
        page += 1
    return repos

def _gh_delete_repo(token: str, owner: str, repo: str) -> Tuple[bool, str]:
    code, raw = _gh_request("DELETE", f"https://api.github.com/repos/{owner}/{repo}", token)
    if code == 204:
        return True, ""
    return False, raw


# ---------------------------
# Identity helper
# ---------------------------

def _get_identity(interactive: bool, p: PFunc) -> Optional[GitIdentity]:
    tok = _get_saved_token()
    if not tok and interactive:
        tok = _prompt("GitHub token (PAT)", default="").strip()
        if tok:
            _set_saved_token(tok)

    if not tok:
        return None

    user = _gh_username(tok)
    if not user:
        return None

    return GitIdentity(tok, user)


# ---------------------------
# Update/Force arg parsing (FIXES your log issue)
# ---------------------------

def _looks_like_repo_spec_string(s: str) -> bool:
    if not s:
        return False
    t = s.strip()
    if "github.com" in t.lower():
        return True
    if re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", t):
        return True
    if re.match(r"^git@github\.com:[^/]+/[^/]+(\.git)?$", t, re.I):
        return True
    return False

def _parse_update_like_args(
    toks: List[str],
    start_index: int,
) -> Tuple[Optional[str], Optional[str], List[str]]:
    """
    For commands: update / force update / debug update
    Returns: (repo_spec_or_none, message_or_none, add_paths)

    Rules (less foot-guns):
    - If first token looks like owner/repo or URL => repo_spec
    - Else if first token contains spaces => treat it as message (NOT repo)
    - Else if first token is --add => repo_spec none, message none
    - Else: treat as repo_spec (back-compat)
    - Remaining tokens (excluding --add path pairs) become message if not already set
    """
    repo_spec: Optional[str] = None
    msg: Optional[str] = None
    add_paths: List[str] = []

    i = start_index
    if i < len(toks) and not toks[i].startswith("--"):
        first = toks[i]
        if _looks_like_repo_spec_string(first):
            repo_spec = first
            i += 1
        else:
            # IMPORTANT FIX: quoted messages like "Update 1" become one token with a space
            if " " in first.strip():
                msg = first.strip()
                i += 1
            else:
                # ambiguous single-word: keep old behavior (repo first)
                repo_spec = first
                i += 1

    while i < len(toks):
        t = toks[i]
        if t.lower() == "--add" and (i + 1) < len(toks):
            add_paths.append(toks[i + 1])
            i += 2
            continue

        rest = " ".join(toks[i:]).strip()
        if rest:
            msg = rest.strip().strip('"').strip("'")
        break

    return repo_spec, msg, add_paths


# ---------------------------
# FORCE / DEBUG engine
# ---------------------------

class _ForceFail(Exception):
    def __init__(self, msg: str, steps: List[str], last_out: str = ""):
        super().__init__(msg)
        self.msg = msg
        self.steps = steps
        self.last_out = last_out

def _log_step(steps: List[str], text: str) -> None:
    steps.append(text)

def _debug_snapshot(root: Path, identity: Optional[GitIdentity]) -> str:
    parts: List[str] = []

    def add(title: str, rc_out: Tuple[int, str]) -> None:
        rc, out = rc_out
        parts.append(f"=== {title} (rc={rc}) ===")
        parts.append(out)

    add("git --version", _git_run(["--version"], cwd=root))
    add("git status -sb", _git_run(["status", "-sb"], cwd=root))
    add("git status --porcelain", _git_run(["status", "--porcelain"], cwd=root))
    add("git branch -vv", _git_run(["branch", "-vv"], cwd=root))
    add("git remote -v", _git_run(["remote", "-v"], cwd=root))
    add("git log --oneline -5", _git_run(["log", "--oneline", "-5"], cwd=root))

    lock = root / ".git" / "index.lock"
    parts.append(f"index.lock: {'present' if lock.exists() else 'missing'} ({lock})")

    remote = _get_origin_remote(root)
    parts.append(f"origin url: {_safe_remote_str(remote) or '(none)'}")
    if remote:
        parts.append(f"origin web: {_remote_web_url(remote) or '(n/a)'}")
        parts.append(f"remote HEAD branch: {_remote_head_branch(root, identity) or '(unknown)'}")

    return "\n".join(parts)

def _force_prepare_repo(
    root: Path,
    identity: Optional[GitIdentity],
    steps: List[str],
    target_remote: Optional[str],
    prefer_branch: str,
) -> str:
    _ensure_repo_initialized(root)
    _log_step(steps, "ensure repo initialized")

    removed, msg = _maybe_remove_index_lock(root)
    if removed:
        _log_step(steps, msg)
    elif msg:
        _log_step(steps, msg)

    if target_remote:
        if _looks_like_placeholder_remote(target_remote):
            raise _ForceFail("Target remote contains placeholder '<you>'", steps, target_remote)
        _set_origin_remote(root, target_remote)
        _log_step(steps, f"set origin -> {_safe_remote_str(target_remote)}")
        
        
    _gitignore_add(root, DEFAULT_GITIGNORE_PATTERNS)
    _log_step(steps, "ensure .gitignore")

    _ensure_git_user_config(root, identity)
    _log_step(steps, "ensure git user.name/user.email")

    branch = (prefer_branch or "main").strip() or "main"
    if _get_origin_remote(root):
        rh = _remote_head_branch(root, identity)
        if rh:
            branch = rh
            _log_step(steps, f"remote head branch detected -> {branch}")

    rc, _ = _ensure_branch(root, branch)
    _log_step(steps, f"checkout/switch branch -> {branch} (rc={rc})")

    _ensure_readme_if_empty(root)
    _log_step(steps, "ensure README if empty")

    if not _has_commits(root):
        _git_run(["add", "-A"], cwd=root)
        rc2, out2 = _git_run(["commit", "--allow-empty", "-m", "Initial commit"], cwd=root)
        if rc2 != 0 and "nothing to commit" not in out2.lower():
            raise _ForceFail("Failed to create initial commit", steps, out2)
        _log_step(steps, "ensure initial commit")

    return branch

def _force_push_with_retries(root: Path, branch: str, identity: Optional[GitIdentity], steps: List[str]) -> None:
    rc, out = _push_branch(root, branch, identity)
    _log_step(steps, f"push --set-upstream origin {branch} (rc={rc})")
    if rc == 0:
        return

    low = (out or "").lower()

    if "placeholder" in low and "<you>" in low:
        raise _ForceFail("Origin remote is a placeholder", steps, out)

    # Fix: "src refspec X does not match any"
    if "src refspec" in low or "does not match any" in low:
        _ensure_readme_if_empty(root)
        _git_run(["add", "-A"], cwd=root)
        _git_run(["commit", "--allow-empty", "-m", "Init (force)"], cwd=root)
        _log_step(steps, "refspec fix: ensured commit exists")
        rc2, out2 = _push_branch(root, branch, identity)
        _log_step(steps, f"push retry after refspec fix (rc={rc2})")
        if rc2 == 0:
            return
        out = out2
        low = (out or "").lower()

    # Fix: non-fast-forward
    if ("non-fast-forward" in low) or ("fetch first" in low) or ("rejected" in low) or ("updates were rejected" in low):
        rc3, out3 = _pull_rebase(root, branch, identity)
        _log_step(steps, f"pull --rebase origin {branch} (rc={rc3})")
        if rc3 == 0:
            rc4, out4 = _push_branch(root, branch, identity)
            _log_step(steps, f"push after rebase (rc={rc4})")
            if rc4 == 0:
                return
            out = out4
            low = (out or "").lower()

        # Last resort: force-with-lease
        rc5, out5 = _push_force_with_lease(root, branch, identity)
        _log_step(steps, f"push --force-with-lease origin {branch} (rc={rc5})")
        if rc5 == 0:
            return
        out = out5

    raise _ForceFail("Push still failing after auto-fixes", steps, out)

def _run_force_flow(
    root: Path,
    p: PFunc,
    identity: Optional[GitIdentity],
    target_remote: Optional[str],
    prefer_branch: str,
    commit_msg: str,
    add_paths: Optional[List[str]],
    debug_always: bool,
) -> bool:
    steps: List[str] = []
    try:
        branch = _force_prepare_repo(
            root=root,
            identity=identity,
            steps=steps,
            target_remote=target_remote,
            prefer_branch=prefer_branch,
        )

        if add_paths:
            res = _commit_only_paths(root, add_paths, commit_msg)
            _log_step(steps, f"commit partial: {commit_msg}")
            if res.startswith("❌"):
                raise _ForceFail("Commit failed", steps, res)
        else:
            res = _commit_if_needed(root, commit_msg)
            _log_step(steps, f"commit: {commit_msg}")
            if res.startswith("❌"):
                raise _ForceFail("Commit failed", steps, res)

        _force_push_with_retries(root, branch, identity, steps)

        if debug_always:
            p("[green]✅ DEBUG completed.[/green]")
            p("\n".join(f"- {x}" for x in steps))

        return True

    except _ForceFail as e:
        snap = _debug_snapshot(root, identity)

        report = []
        report.append("=== STEPS EXECUTED ===")
        report.extend(f"- {x}" for x in e.steps)
        report.append("")
        report.append("=== LAST ERROR OUTPUT ===")
        report.append(e.last_out or "(none)")
        report.append("")
        report.append("=== SNAPSHOT ===")
        report.append(snap)

        full = "\n".join(report)
        fp = _write_debug_report(root, "CMC GIT FORCE FAILED", full)

        p("[red]🧨 Git FORCE failed.[/red]")
        p("Full debug dump (also saved to a file):")
        if fp:
            p(f"📄 {fp}")
        p(full)
        return False


# ---------------------------
# Public entrypoint
# ---------------------------

def handle_git_commands(raw: str, low: str, cwd: Union[str, Path], p: PFunc, RICH: bool = False, console=None) -> bool:
    """
    Return True if matched (so CMC stops parsing further).
    """
    if not (low == "git" or low.startswith("git ")):
        return False

    if not _git_installed():
        p("[red]❌ Git is not installed or not found in PATH.[/red]")
        p("Fix: install Git for Windows, then restart terminals/CMC.")
        return True

    start = Path(cwd)
    root = _resolve_repo_root(start)

    toks = _tokens(raw)
    if len(toks) < 2:
        p("[yellow]Try: git upload | git update | git download | git repo list | git doctor[/yellow]")
        p("[yellow]Or run any normal git command: git branch -a, git add ., git commit -m \"x\", git push[/yellow]")
        return True

    cmd = toks[1].lower()

    # --------------------------------------------------------
    # git doctor
    # --------------------------------------------------------
    if cmd == "doctor":
        msgs = []
        rc, out = _git_run(["--version"], cwd=root)
        msgs.append(f"git: {'OK' if rc == 0 else out}")
        msgs.append(f"CMC folder: {start}")
        msgs.append(f"repo root used: {root}")
        msgs.append(f".git: {'exists' if (root / '.git').exists() else 'missing'}")

        remote = _get_origin_remote(root)
        msgs.append(f"origin: {_safe_remote_str(remote) or '(none)'}")
        web = _remote_web_url(remote) if remote else None
        if web:
            msgs.append(f"web: {web}")

        tok = _get_saved_token()
        msgs.append(f"token: {'present' if bool(tok) else 'missing'} ({GIT_CFG})")

        mapping = _remembered_repo(root)
        if mapping:
            msgs.append(f"saved mapping: {mapping.get('owner','?')}/{mapping.get('name','?')}")
        else:
            msgs.append("saved mapping: (none)")

        p("\n".join(msgs))
        return True

    # --------------------------------------------------------
    # git open
    # --------------------------------------------------------
    if cmd == "open":
        remote = _get_origin_remote(root)
        web = _remote_web_url(remote)
        if not web:
            p("[yellow]No GitHub origin detected. Use: git link owner/repo[/yellow]")
            return True
        webbrowser.open_new_tab(web)
        p(f"🌐 Opened: {web}")
        return True

    # --------------------------------------------------------
    # git link <owner/repo|url>
    # --------------------------------------------------------
    if cmd == "link":
        if len(toks) < 3:
            p("[red]❌ Usage:[/red] git link <owner>/<repo>  (or GitHub URL)")
            return True
        spec = toks[2].strip()
        parsed = _parse_repo_spec(spec)
        if not parsed:
            p("[red]❌ Not a valid GitHub repo spec.[/red] Use owner/repo or a github.com URL.")
            return True
        owner, repo = parsed
        remote = f"https://github.com/{owner}/{repo}.git"
        _ensure_repo_initialized(root)
        _set_origin_remote(root, remote)
        _remember_repo(root, owner, repo, remote)
        p(f"✅ Linked origin to: https://github.com/{owner}/{repo}.git")
        return True

    # --------------------------------------------------------
    # git repo list [all|mine]
    # --------------------------------------------------------
    if cmd == "repo" and len(toks) >= 3 and toks[2].lower() == "list":
        mode = toks[3].lower() if len(toks) >= 4 else "all"

        ident = _get_identity(interactive=True, p=p)
        if not ident:
            p("[red]❌ Bad credentials or missing token.[/red]")
            p("Fix: create a GitHub PAT (classic) with repo scope (or a fine-grained token with repo access).")
            return True

        repos = _gh_list_repos(ident.token)
        if not repos:
            p("No repositories found (or token has no access).")
            return True

        if mode == "mine":
            repos = [r for r in repos if (r.get("owner", {}) or {}).get("login", "").lower() == ident.username.lower()]

        p("Your accessible GitHub repositories (includes Classroom/org/collab):")
        for r in repos[:200]:
            owner = (r.get("owner", {}) or {}).get("login", "?")
            name = r.get("name", "?")
            vis = "private" if r.get("private") else "public"
            fork = " fork" if r.get("fork") else ""
            p(f"- {owner}/{name} ({vis}){fork}")

        if len(repos) > 200:
            p(f"...and {len(repos) - 200} more (showing 200). Use: git repo list mine")
        return True

    # --------------------------------------------------------
    # git repo delete <owner/repo|repoName>
    # --------------------------------------------------------
    if cmd == "repo" and len(toks) >= 4 and toks[2].lower() == "delete":
        target = toks[3].strip()
        ident = _get_identity(interactive=True, p=p)
        if not ident:
            p("[red]❌ Bad credentials or missing token.[/red]")
            return True

        parsed = _parse_repo_spec(target)
        if parsed:
            owner, repo = parsed
        else:
            owner, repo = ident.username, _sanitize_repo_name(target)

        p("⚠️ This will permanently delete on GitHub:")
        p(f"  {owner}/{repo}")
        confirm = input("Type DELETE to confirm: ").strip()
        if confirm != "DELETE":
            p("❌ Cancelled.")
            return True

        ok, err = _gh_delete_repo(ident.token, owner, repo)
        if ok:
            p("🗑️ Repository deleted on GitHub.")
        else:
            p("[red]❌ Failed to delete repository.[/red]")
            p(err)
        return True

    # --------------------------------------------------------
    # git download <owner/repo|url>
    # --------------------------------------------------------
    if cmd in ("download", "clone"):
        if len(toks) < 3:
            p("[red]❌ Usage:[/red] git download <owner>/<repo> (or GitHub URL)")
            return True

        spec = toks[2].strip()
        parsed = _parse_repo_spec(spec)
        if not parsed:
            p("[red]❌ Use owner/repo format or a github.com URL.[/red]")
            return True

        owner, repo = parsed
        target = start / repo
        if target.exists():
            p(f"[red]❌ Folder already exists:[/red] {target}")
            return True

        url = f"https://github.com/{owner}/{repo}.git"
        p(f"⬇️ Cloning {url}")

        rc, out = _git_run(["clone", url, repo], cwd=start)
        if rc == 0:
            p(f"📁 Installed to: {target}")
            return True

        if _looks_like_auth_error(out):
            ident = _get_identity(interactive=True, p=p)
            if ident:
                rc2, out2 = _git_run(["clone", url, repo], cwd=start, identity=ident)
                if rc2 == 0:
                    p(f"📁 Installed to: {target}")
                    return True
                p(f"[red]❌ Clone failed:[/red]\n{out2}")
                return True

        p(f"[red]❌ Clone failed:[/red]\n{out}")
        return True

    # --------------------------------------------------------
    # git upload  (create NEW repo under your account)
    # --------------------------------------------------------
    if cmd == "upload":
        default_repo = _sanitize_repo_name(root.name)
        repo_name = _sanitize_repo_name(_prompt("Repository name", default=default_repo))

        public = _prompt_public(default_public=True)
        private = not public

        ident = _get_identity(interactive=True, p=p)
        if not ident:
            p("[red]❌ Bad credentials.[/red] Token can't access GitHub API (/user).")
            p("Fix: create a GitHub PAT (classic) with repo scope, paste it when asked.")
            return True

        ok, msg = _gh_create_repo(ident.token, repo_name, private=private)
        if not ok:
            p(f"[red]❌ GitHub API error:[/red]\n{msg}")
            return True

        remote = f"https://github.com/{ident.username}/{repo_name}.git"

        _ensure_repo_initialized(root)
        
        _gitignore_add(root, DEFAULT_GITIGNORE_PATTERNS)

        _set_origin_remote(root, remote)

        # ensure main branch to avoid "src refspec main does not match any"
        _ensure_branch(root, "main")

        big = _warn_big_files(root)
        if big:
            p("⚠️ Large files detected (>100MB). GitHub may reject unless you use LFS:")
            for b in big[:25]:
                p(f"  - {b}")
            if len(big) > 25:
                p(f"  ... and {len(big) - 25} more")

        _ensure_readme_if_empty(root)

        commit_msg = _prompt("Commit message", default="Initial commit")
        p(_commit_if_needed(root, commit_msg))

        rc, out = _push_branch(root, "main", ident)
        if rc == 0:
            _remember_repo(root, ident.username, repo_name, remote)
            p(f"✅ Uploaded: https://github.com/{ident.username}/{repo_name} ({'public' if public else 'private'})")
            webbrowser.open_new_tab(f"https://github.com/{ident.username}/{repo_name}")
        else:
            p(f"[red]❌ Push failed:[/red]\n{out}")
        return True

    # --------------------------------------------------------
    # git update [repoSpec] ["msg"] [--add <path>]
    # FIXED: "git update 'Update 1'" will be treated as message, not repo.
    # --------------------------------------------------------
    if cmd == "update":
        repo_spec, msg_arg, add_paths = _parse_update_like_args(toks, start_index=2)

        remote = _get_origin_remote(root)
        if _looks_like_placeholder_remote(remote):
            p("[red]❌ origin contains '<you>' placeholder.[/red] Fix it with: git link Wiglol/RepoName")
            return True

        if repo_spec and _looks_like_repo_spec_string(repo_spec):
            parsed = _parse_repo_spec(repo_spec)
            if not parsed:
                p("[red]❌ Invalid repo spec.[/red] Use owner/repo or github.com URL.")
                return True
            owner, repo_name = parsed
            remote = f"https://github.com/{owner}/{repo_name}.git"
            _ensure_repo_initialized(root)
            _set_origin_remote(root, remote)
            _remember_repo(root, owner, repo_name, remote)

        elif repo_spec and not _looks_like_repo_spec_string(repo_spec):
            # Back-compat: single-word repo name
            # Only do this if we have an owner from mapping/identity.
            repo_name = _sanitize_repo_name(repo_spec)
            mapping = _remembered_repo(root) or {}
            owner = mapping.get("owner")
            if not owner:
                ident_tmp = _get_identity(interactive=False, p=p)
                owner = ident_tmp.username if ident_tmp else None
            if not owner:
                p("[yellow]No owner known for repoName shortcut.[/yellow] Use: git update owner/repo")
                return True
            remote = f"https://github.com/{owner}/{repo_name}.git"
            _ensure_repo_initialized(root)
            _set_origin_remote(root, remote)
            _remember_repo(root, owner, repo_name, remote)

        if not remote:
            mapping = _remembered_repo(root)
            if mapping and mapping.get("remote"):
                remote = str(mapping["remote"])
                _ensure_repo_initialized(root)
                _set_origin_remote(root, remote)

        if not remote:
            p("[yellow]No remote set for this folder.[/yellow]")
            p("Fix: git link owner/repo   OR   git upload")
            return True

        ident = _get_identity(interactive=False, p=p)
        msg = msg_arg or _auto_update_message()

        if add_paths:
            p(_commit_only_paths(root, add_paths, msg))
        else:
            p(_commit_if_needed(root, msg))

        rc, out = _push(root, ident)
        if rc == 0:
            web = _remote_web_url(remote)
            if web:
                p(f"✅ Updated: {web}")
                webbrowser.open_new_tab(web)
            else:
                p("✅ Updated.")
        else:
            p(f"[red]❌ Push failed:[/red]\n{out}")
            p("Tip: if this is GitHub Classroom, make sure origin points to the classroom repo:")
            p("  git link prakticum3k/your-repo-name")
        return True

    # --------------------------------------------------------
    # git force <upload|update> ...
    # git debug <upload|update> ...
    # --------------------------------------------------------
    if cmd in ("force", "debug"):
        if len(toks) < 3:
            p("[red]❌ Usage:[/red] git force upload | git force update [owner/repo|url|repoName] [\"msg\"] [--add <path>]")
            return True

        mode_debug = (cmd == "debug")
        sub = toks[2].lower()

        # ---- force/debug upload ----
        if sub == "upload":
            default_repo = _sanitize_repo_name(root.name)
            repo_name = _sanitize_repo_name(_prompt("Repository name", default=default_repo))
            public = _prompt_public(default_public=True)
            private = not public

            ident = _get_identity(interactive=True, p=p)
            if not ident:
                p("[red]❌ Bad credentials.[/red] Token can't access GitHub API (/user).")
                return True

            ok, msg = _gh_create_repo(ident.token, repo_name, private=private)
            if not ok:
                p(f"[red]❌ GitHub API error:[/red]\n{msg}")
                return True

            remote = f"https://github.com/{ident.username}/{repo_name}.git"

            big = _warn_big_files(root)
            if big:
                p("⚠️ Large files detected (>100MB). GitHub may reject unless you use LFS:")
                for b in big[:25]:
                    p(f"  - {b}")
                if len(big) > 25:
                    p(f"  ... and {len(big) - 25} more")

            commit_msg = _prompt("Commit message", default="Initial commit (force)")
            ok2 = _run_force_flow(
                root=root,
                p=p,
                identity=ident,
                target_remote=remote,
                prefer_branch="main",
                commit_msg=commit_msg,
                add_paths=None,
                debug_always=mode_debug,
            )
            if ok2:
                _remember_repo(root, ident.username, repo_name, remote)
                web = f"https://github.com/{ident.username}/{repo_name}"
                p(f"✅ Force uploaded: {web}")
                webbrowser.open_new_tab(web)
            return True

        # ---- force/debug update ----
        if sub == "update":
            repo_spec, msg_arg, add_paths = _parse_update_like_args(toks, start_index=3)

            remote = _get_origin_remote(root)
            if _looks_like_placeholder_remote(remote):
                # We'll still allow overriding via repo_spec, but if repo_spec is missing we stop.
                if not repo_spec:
                    p("[red]❌ origin contains '<you>' placeholder.[/red] Fix it with: git link Wiglol/RepoName OR pass a real repo to force update.")
                    return True

            if repo_spec and _looks_like_repo_spec_string(repo_spec):
                parsed = _parse_repo_spec(repo_spec)
                if not parsed:
                    p("[red]❌ Invalid repo spec.[/red] Use owner/repo or github.com URL.")
                    return True
                owner, repo_name = parsed
                remote = f"https://github.com/{owner}/{repo_name}.git"
                _ensure_repo_initialized(root)
                _set_origin_remote(root, remote)
                _remember_repo(root, owner, repo_name, remote)

            elif repo_spec and not _looks_like_repo_spec_string(repo_spec):
                repo_name = _sanitize_repo_name(repo_spec)
                mapping = _remembered_repo(root) or {}
                owner = mapping.get("owner")
                if not owner:
                    ident_tmp = _get_identity(interactive=False, p=p)
                    owner = ident_tmp.username if ident_tmp else None
                if not owner:
                    p("[yellow]No owner known for repoName shortcut.[/yellow] Use: git force update owner/repo")
                    return True
                remote = f"https://github.com/{owner}/{repo_name}.git"
                _ensure_repo_initialized(root)
                _set_origin_remote(root, remote)
                _remember_repo(root, owner, repo_name, remote)

            if not remote:
                mapping = _remembered_repo(root)
                if mapping and mapping.get("remote"):
                    remote = str(mapping["remote"])
                    _ensure_repo_initialized(root)
                    _set_origin_remote(root, remote)

            if not remote:
                p("[yellow]No remote set for this folder.[/yellow]")
                p("Fix: git link owner/repo   OR   git force upload")
                return True

            ident = _get_identity(interactive=True, p=p)
            msg = msg_arg or _auto_update_message()

            ok2 = _run_force_flow(
                root=root,
                p=p,
                identity=ident,
                target_remote=remote,
                prefer_branch="main",
                commit_msg=msg,
                add_paths=add_paths if add_paths else None,
                debug_always=mode_debug,
            )
            if ok2:
                web = _remote_web_url(remote)
                if web:
                    p(f"✅ Force updated: {web}")
                    webbrowser.open_new_tab(web)
                else:
                    p("✅ Force updated.")
            return True

        p("[red]❌ Unknown force/debug subcommand.[/red] Use: git force upload | git force update")
        return True

    # --------------------------------------------------------
    # Default: Pass-through to real git for EVERYTHING else.
    # --------------------------------------------------------
    args = toks[1:]  # everything after the leading "git"
    ident = _get_identity(interactive=False, p=p)

    use_ident = None
    if args and args[0].lower() in ("push", "fetch", "pull", "clone"):
        remote = _get_origin_remote(root)
        if remote and remote.startswith("https://") and _is_github_remote(remote) and ident:
            use_ident = ident

    rc, out = _git_run(args, cwd=root, identity=use_ident)
    p(out)
    return True
