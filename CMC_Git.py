import base64
import os
import datetime
import json
import re
import shutil
import subprocess
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Tuple, Union

# ------------------------------------------------------------
# CMC_Git.py (drop-in module for Computer Main Centre)
#
# Designed for CMC where `cd` changes an INTERNAL CWD variable
# (and might not call os.chdir()). Therefore this module ALWAYS
# uses the `cwd` argument that CMC passes in.
#
# Commands (NO slash):
#   git upload
#   git update [RepoName] ["commit message"]
#   git status
#   git log
#   git doctor
#   git download <owner>/<repo>  (clones to Desktop)
#
# Behavior:
# - First run asks for a GitHub token (PAT) and stores it in:
#     %USERPROFILE%\.ai_helper\github.json
# - `git upload` asks repo name + "Public? (y/n)" and publishes
#   the current folder to GitHub.
# - `git update` with no repo name uses the saved folder→repo mapping.
# ------------------------------------------------------------

PFunc = Callable[[str], None]

GIT_CFG = Path.home() / ".ai_helper" / "github.json"
GIT_CFG.parent.mkdir(parents=True, exist_ok=True)


@dataclass
class GitIdentity:
    token: str
    username: str


# ---------------------------
# Config helpers
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


def _sanitize_repo_name(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name)
    name = name.strip("-.")
    return name or "repo"


def _prompt(msg: str, default: Optional[str] = None) -> str:
    if default is not None and default != "":
        raw = input(f"{msg} [{default}]: ").strip()
        return raw or default
    return input(f"{msg}: ").strip()


def _prompt_public(default_public: bool = True) -> bool:
    # User asked: "public? y/s" – we interpret as y/n.
    # Accept 's' as no (just in case you meant "secret").
    d = "y" if default_public else "n"
    raw = input(f"Public repository? (y/n) [{d}]: ").strip().lower()
    if not raw:
        return default_public
    if raw.startswith("y"):
        return True
    if raw.startswith("n") or raw.startswith("s"):
        return False
    return default_public


def _tokens(raw: str) -> list[str]:
    try:
        return shlex.split(raw, posix=False)
    except Exception:
        return raw.strip().split()


def _get_token(interactive: bool = True) -> Optional[str]:
    data = _cfg_load()
    tok = (data.get("token") or "").strip()
    if tok:
        return tok
    if not interactive:
        return None

    tok = _prompt("GitHub token (PAT)", default="").strip()
    if tok:
        data["token"] = tok
        _cfg_save(data)
        return tok
    return None


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
# Git helpers
# ---------------------------

def _git_installed() -> bool:
    return bool(shutil.which("git"))


def _git_run(args: list[str], cwd: Union[str, Path], identity: Optional[GitIdentity] = None) -> Tuple[int, str]:
    """Run git. If identity is provided, uses a non-persistent auth header."""
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
        p = Path(out.strip())
        if p.exists():
            return p
    return start


def _ensure_repo_initialized(root: Path) -> None:
    if not (root / ".git").exists():
        _git_run(["init"], cwd=root)


def _ensure_main_branch(root: Path) -> None:
    _git_run(["branch", "-M", "main"], cwd=root)


def _set_remote(root: Path, remote_url: str) -> None:
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


def _gitignore_add(root: Path, patterns: list[str]) -> None:
    gi = root / ".gitignore"
    try:
        lines = gi.read_text(encoding="utf-8", errors="ignore").splitlines() if gi.exists() else []
    except Exception:
        lines = []

    changed = False
    for ptn in patterns:
        if ptn not in lines:
            lines.append(ptn)
            changed = True

    if changed:
        gi.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _warn_big_files(root: Path, limit_mb: int = 100) -> list[str]:
    limit = limit_mb * 1024 * 1024
    big: list[str] = []
    try:
        for fp in root.rglob("*"):
            if ".git" in fp.parts:
                continue
            if fp.is_file() and fp.stat().st_size > limit:
                big.append(str(fp.relative_to(root)))
    except Exception:
        pass
    return big



def _desktop_dir() -> Path:
    """Best-effort Desktop folder (supports OneDrive Desktop too)."""
    home = Path.home()
    d1 = home / "Desktop"
    if d1.exists():
        return d1
    d2 = home / "OneDrive" / "Desktop"
    if d2.exists():
        return d2
    return home


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
            if repo.lower().endswith(".git"):
                repo = repo[:-4]
            return owner, repo

    if "/" in s:
        owner, repo = s.split("/", 1)
        owner = owner.strip()
        repo = repo.strip()
        if repo.lower().endswith(".git"):
            repo = repo[:-4]
        if owner and repo:
            return owner, repo

    return None


def _looks_like_auth_error(out: str) -> bool:
    o = (out or "").lower()
    markers = [
        "authentication failed",
        "fatal: could not read username",
        "fatal: could not read password",
        "http 401",
        "http 403",
        "denied",
        "repository not found",
    ]
    return any(m in o for m in markers)


def _ensure_readme_if_empty(root: Path) -> None:
    # If there are no commits AND no changes staged, create README so first push exists.
    if _has_commits(root):
        return

    _git_run(["add", "-A"], cwd=root)
    if _status_porcelain(root):
        return

    readme = root / "README.md"
    if not readme.exists():
        readme.write_text(f"# {root.name}\n", encoding="utf-8")
    _git_run(["add", "README.md"], cwd=root)
    
    
    
def _gh_list_repos(token: str) -> list[dict]:
    repos = []
    page = 1
    while True:
        code, raw = _gh_request(
            "GET",
            f"https://api.github.com/user/repos?per_page=100&page={page}",
            token
        )
        if code != 200:
            break
        data = json.loads(raw)
        if not data:
            break
        repos.extend(data)
        page += 1
    return repos
    
    
    
def _gh_delete_repo(token: str, owner: str, repo: str) -> bool:
    code, _ = _gh_request(
        "DELETE",
        f"https://api.github.com/repos/{owner}/{repo}",
        token
    )
    return code == 204




def _commit_if_needed(root: Path, msg: str) -> str:
    _git_run(["add", "-A"], cwd=root)
    rc, out = _git_run(["commit", "-m", msg], cwd=root)
    if rc != 0 and "nothing to commit" in out.lower():
        return "ℹ️ Nothing to commit."
    if rc != 0:
        return f"❌ Commit failed:\n{out}"
    return "✅ Committed."


def _push_main(root: Path, identity: GitIdentity) -> Tuple[int, str]:
    _ensure_main_branch(root)

    # 1) Try with non-persistent auth header
    rc, out = _git_run(["push", "--set-upstream", "origin", "main"], cwd=root, identity=identity)
    if rc == 0:
        return rc, out

    # 2) Fallback without header (Git Credential Manager / browser might handle)
    auth_markers = [
        "authentication failed",
        "fatal: could not read username",
        "fatal: could not read password",
        "http 401",
        "http 403",
        "denied",
    ]
    if any(m in out.lower() for m in auth_markers):
        rc2, out2 = _git_run(["push", "--set-upstream", "origin", "main"], cwd=root, identity=None)
        if rc2 != 0:
            return rc2, out2 or out
        return rc2, out2

    return rc, out


def _auto_update_message() -> str:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"Update {now}"


# ---------------------------
# GitHub API helpers
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
        with urllib.request.urlopen(req, timeout=20) as resp:
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
    # 422: already exists -> treat as ok
    if code == 422:
        return True, "already-exists"
    return False, raw


# ---------------------------
# Public entrypoint
# ---------------------------

def handle_git_commands(raw: str, low: str, cwd: Union[str, Path], p: PFunc, RICH: bool = False, console=None) -> bool:
    """Return True if matched (so CMC stops parsing further)."""

    # ONLY: git ... (no slash)
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
        p("[yellow]Try: git upload | git update [RepoName] | git status | git log[/yellow]")
        return True

    cmd = toks[1].lower()

    # ---- info commands ----
    if cmd == "status":
        _, out = _git_run(["status"], cwd=root)
        p(out)
        return True

    if cmd == "log":
        _, out = _git_run(["log", "--oneline", "-n", "10"], cwd=root)
        p(out)
        return True

    if cmd == "doctor":
        msgs = []
        rc, out = _git_run(["--version"], cwd=root)
        msgs.append(f"git: {'OK' if rc == 0 else out}")
        msgs.append(f"CMC folder: {start}")
        msgs.append(f"repo root used: {root}")
        msgs.append(f".git: {'exists' if (root / '.git').exists() else 'missing'}")
        tok = _get_token(interactive=False)
        msgs.append(f"token: {'present' if tok else 'missing'} ({GIT_CFG})")
        mapping = _remembered_repo(root)
        if mapping:
            msgs.append(f"saved mapping: {mapping.get('owner','?')}/{mapping.get('name','?')}")
        p("\n".join(msgs))
        return True
        
        
       # ---- GitHub repo management ----
    if cmd == "repo" and len(toks) >= 3 and toks[2] == "list":
        tok = _get_token(interactive=True)
        if not tok:
            p("[red]❌ No token provided.[/red]")
            return True

        user = _gh_username(tok)
        if not user:
            p("[red]❌ Bad credentials.[/red]")
            return True

        repos = _gh_list_repos(tok)
        if not repos:
            p("No repositories found.")
            return True

        p("Your GitHub repositories:")
        for r in repos:
            vis = "private" if r.get("private") else "public"
            p(f"- {r['name']} ({vis})")
        return True

    if cmd == "repo" and len(toks) >= 4 and toks[2] == "delete":
        repo = toks[3].strip()
        if not repo:
            p("[red]❌ Missing repo name.[/red]")
            return True

        tok = _get_token(interactive=True)
        if not tok:
            p("[red]❌ No token provided.[/red]")
            return True

        user = _gh_username(tok)
        if not user:
            p("[red]❌ Bad credentials.[/red]")
            return True

        p("⚠️ This will permanently delete:")
        p(f"  {user}/{repo}")
        confirm = input("Type DELETE to confirm: ").strip()
        if confirm != "DELETE":
            p("❌ Cancelled.")
            return True

        if _gh_delete_repo(tok, user, repo):
            p("🗑️ Repository deleted.")
        else:
            p("[red]❌ Failed to delete repository.[/red]")
        return True




     # ---- git download / clone ----
    if cmd in ("download", "clone"):
        if len(toks) < 3:
            p("[red]❌ Usage:[/red] git download <owner>/<repo>")
            return True

        spec = toks[2].strip()

        # Accept full GitHub URLs too
        if spec.startswith("http://") or spec.startswith("https://"):
            if "github.com/" not in spec:
                p("[red]❌ Not a GitHub URL.[/red]")
                return True
            spec = spec.split("github.com/", 1)[1]
            spec = spec.replace(".git", "").strip("/")

        if "/" not in spec:
            p("[red]❌ Use owner/repo format.[/red]")
            return True

        owner, repo = spec.split("/", 1)

        target = start / repo
        if target.exists():
            p(f"[red]❌ Folder already exists:[/red] {target}")
            return True

        url = f"https://github.com/{owner}/{repo}.git"
        p(f"⬇️ Cloning {url}")

        try:
            _git_run(["clone", url, repo], cwd=str(start))
            p(f"📁 Installed to: {target}")
        except Exception as e:
            p(f"[red]❌ Clone failed:[/red] {e}")
            return True

        return True



    # ---- git upload ----
    if cmd == "upload":
        default_repo = _sanitize_repo_name(root.name)
        repo = _sanitize_repo_name(_prompt("Repository name", default=default_repo))

        public = _prompt_public(default_public=True)
        private = not public

        tok = _get_token(interactive=True)
        if not tok:
            p("[red]❌ No token provided.[/red]")
            return True

        user = _gh_username(tok)
        if not user:
            p("[red]❌ Bad credentials.[/red] Token can't access GitHub API (/user).")
            p("Fix: create a GitHub PAT (classic) with repo scope, paste it when asked.")
            return True

        ok, msg = _gh_create_repo(tok, repo, private=private)
        if not ok:
            p(f"[red]❌ GitHub API error:[/red]\n{msg}")
            return True

        remote = f"https://github.com/{user}/{repo}.git"

        _ensure_repo_initialized(root)
        _ensure_main_branch(root)
        _gitignore_add(root, ["__pycache__/", "*.pyc", ".venv/", "venv/", "paths.db", "centre_index*.json", "*.log", "*.tmp", ".DS_Store", "Thumbs.db"])
        _set_remote(root, remote)

        big = _warn_big_files(root)
        if big:
            p("⚠️ Large files detected (>100MB). GitHub may reject these unless you use LFS:")
            for b in big[:25]:
                p(f"  - {b}")
            if len(big) > 25:
                p(f"  ... and {len(big) - 25} more")
            p("Tip: add them to .gitignore or use Git LFS.")

        _ensure_readme_if_empty(root)

        commit_msg = _prompt("Commit message", default="Initial commit")
        p(_commit_if_needed(root, commit_msg))

        rc, out = _push_main(root, GitIdentity(tok, user))
        if rc == 0:
            _remember_repo(root, user, repo, remote)
            p(f"✅ Uploaded: {remote} ({'public' if public else 'private'})")
            import webbrowser
            webbrowser.open_new_tab(remote.replace(".git", ""))
        else:
            p(f"[red]❌ Push failed:[/red]\n{out}")
            p("Tip: run `git doctor` to confirm CMC is using the correct folder.")
        return True

    # ---- git update ----
    if cmd == "update":
        repo_arg = toks[2] if len(toks) >= 3 else None
        msg_arg = None
        if len(toks) >= 4:
            msg_arg = " ".join(toks[3:]).strip().strip('"')

        mapping = _remembered_repo(root)
        owner = (mapping.get("owner") if mapping else None) or None
        repo_name = (mapping.get("name") if mapping else None) or None

        if repo_arg:
            if "github.com" in repo_arg.lower():
                repo_name = _sanitize_repo_name(Path(repo_arg).stem)
            else:
                repo_name = _sanitize_repo_name(repo_arg)

        if not repo_name:
            p("[yellow]No repo saved for this folder.[/yellow] Run: git upload")
            return True

        tok = _get_token(interactive=True)
        if not tok:
            p("[red]❌ No token provided.[/red]")
            return True

        user = _gh_username(tok)
        if not user:
            p("[red]❌ Bad credentials.[/red] Token can't access GitHub API (/user).")
            return True

        owner = owner or user
        remote = f"https://github.com/{owner}/{repo_name}.git"

        # Try create if missing (public by default). 422 if exists -> ok.
        _gh_create_repo(tok, repo_name, private=False)

        _ensure_repo_initialized(root)
        _ensure_main_branch(root)
        _set_remote(root, remote)

        msg = msg_arg or _auto_update_message()
        p(_commit_if_needed(root, msg))

        rc, out = _push_main(root, GitIdentity(tok, user))
        if rc == 0:
            _remember_repo(root, owner, repo_name, remote)
            p(f"✅ Updated: {remote}")
            import webbrowser
            webbrowser.open_new_tab(remote.replace(".git", ""))
        else:
            p(f"[red]❌ Push failed:[/red]\n{out}")
        return True

    p("[yellow]Unknown git command. Try: git upload | git update | git status[/yellow]")
    return True
