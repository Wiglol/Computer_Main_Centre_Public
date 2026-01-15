import base64
import datetime
import json
import os
import re
import shutil
import subprocess
import shlex
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Tuple, Union, List

# ------------------------------------------------------------
# CMC_Gitv2.py — Git + GitHub module for Computer Main Centre
#
# Goals:
# - Keep your EASY commands: upload/update/download/repo list/delete/doctor
# - Support GitHub Classroom (org repos, collaborator repos)
# - Add "real git" support: if command isn't recognized, pass-through to git
# - Never print or open token-in-URL links (no token leaks)
#
# Commands:
#   git upload
#   git update [owner/repo|url|repoName] ["commit msg"]
#   git update [owner/repo|url] --add <path> ["commit msg"]   (push only one file/folder)
#   git link <owner/repo|url>                                (set origin to classroom repo)
#   git open                                                  (open origin in browser)
#   git download <owner/repo|url>                             (clone into current CMC folder)
#   git repo list [all|mine]                                  (shows classroom/org/collab too)
#   git repo delete <owner/repo|repoName>
#   git doctor
#
# PLUS: Any normal git command:
#   git status --ignored
#   git branch -a
#   git checkout -b test
#   git add .
#   git commit -m "msg"
#   git push
#   git pull
#   ...everything.
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
    data["token"] = tok.strip()
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
    # Convert remote to browser URL without leaking tokens.
    if not remote:
        return None

    # Strip embedded auth if present
    if "@" in remote and remote.startswith("https://"):
        # https://TOKEN@github.com/owner/repo.git
        remote = "https://" + remote.split("@", 1)[1]

    spec = _parse_repo_spec(remote)
    if spec:
        owner, repo = spec
        return f"https://github.com/{owner}/{repo}"
    return None


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

def _ensure_main_branch(root: Path) -> None:
    _git_run(["branch", "-M", "main"], cwd=root)

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

def _commit_if_needed(root: Path, msg: str) -> str:
    _git_run(["add", "-A"], cwd=root)
    rc, out = _git_run(["commit", "-m", msg], cwd=root)
    if rc != 0 and "nothing to commit" in out.lower():
        return "ℹ️ Nothing to commit."
    if rc != 0:
        return f"❌ Commit failed:\n{out}"
    return "✅ Committed."

def _commit_only_paths(root: Path, paths: List[str], msg: str) -> str:
    # Stage only given paths, commit, do not auto-add all
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
        # stage
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
    # If we can use identity (https github), do so; otherwise normal push.
    remote = _get_origin_remote(root)
    if identity and remote and _is_github_remote(remote) and remote.startswith("https://"):
        rc, out = _git_run(["push"], cwd=root, identity=identity)
        if rc == 0:
            return rc, out
        # fallback without identity (credential manager)
        if _looks_like_auth_error(out):
            return _git_run(["push"], cwd=root, identity=None)
        return rc, out

    return _git_run(["push"], cwd=root, identity=None)

def _push_main(root: Path, identity: Optional[GitIdentity]) -> Tuple[int, str]:
    _ensure_main_branch(root)
    remote = _get_origin_remote(root)
    if identity and remote and _is_github_remote(remote) and remote.startswith("https://"):
        rc, out = _git_run(["push", "--set-upstream", "origin", "main"], cwd=root, identity=identity)
        if rc == 0:
            return rc, out
        if _looks_like_auth_error(out):
            return _git_run(["push", "--set-upstream", "origin", "main"], cwd=root, identity=None)
        return rc, out

    return _git_run(["push", "--set-upstream", "origin", "main"], cwd=root, identity=None)

def _auto_update_message() -> str:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"Update {now}"


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
    # This is the key for GitHub Classroom + org repos:
    # /user/repos with affiliation includes org repos you can access.
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
# Public entrypoint
# ---------------------------

def handle_git_commands(raw: str, low: str, cwd: Union[str, Path], p: PFunc, RICH: bool = False, console=None) -> bool:
    """
    Return True if matched (so CMC stops parsing further).
    """
    # Only handle: git ...
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
        msgs.append(f"origin: {remote or '(none)'}")
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

        # Filter
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
    # git download <owner/repo|url>   (clone into CURRENT CMC folder)
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

        # Try without token first (public repos)
        rc, out = _git_run(["clone", url, repo], cwd=start)
        if rc == 0:
            p(f"📁 Installed to: {target}")
            return True

        # If auth error, try with token identity
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
        _ensure_main_branch(root)

        _gitignore_add(
            root,
            ["__pycache__/", "*.pyc", ".venv/", "venv/", "paths.db", "centre_index*.json", "*.log", "*.tmp", ".DS_Store", "Thumbs.db"]
        )

        _set_origin_remote(root, remote)

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

        rc, out = _push_main(root, ident)
        if rc == 0:
            _remember_repo(root, ident.username, repo_name, remote)
            p(f"✅ Uploaded: https://github.com/{ident.username}/{repo_name} ({'public' if public else 'private'})")
            webbrowser.open_new_tab(f"https://github.com/{ident.username}/{repo_name}")
        else:
            p(f"[red]❌ Push failed:[/red]\n{out}")
        return True

    # --------------------------------------------------------
    # git update [repoSpec] ["msg"] [--add <path>]
    # - Does NOT create repos (important for Classroom).
    # - If you're inside an existing repo with origin set, it uses that.
    # - If you give owner/repo or a URL, it links origin to that repo and pushes there.
    # --------------------------------------------------------
    if cmd == "update":
        repo_spec = None
        add_paths: List[str] = []
        msg_arg = None

        # Parse flags / args
        # Examples:
        #   git update
        #   git update owner/repo
        #   git update owner/repo "msg"
        #   git update owner/repo --add somefile.png "msg"
        i = 2
        if len(toks) >= 3 and not toks[2].startswith("--"):
            repo_spec = toks[2]
            i = 3

        while i < len(toks):
            t = toks[i]
            if t.lower() == "--add" and (i + 1) < len(toks):
                add_paths.append(toks[i + 1])
                i += 2
                continue
            # everything else becomes commit message (joined)
            msg_arg = " ".join(toks[i:]).strip().strip('"')
            break

        # Determine remote
        remote = _get_origin_remote(root)

        # If user supplied a repo spec, force-link origin to it
        if repo_spec:
            parsed = _parse_repo_spec(repo_spec)
            if not parsed:
                # maybe they typed just repoName -> use mapping owner or token user
                repo_name = _sanitize_repo_name(repo_spec)
                mapping = _remembered_repo(root) or {}
                owner = mapping.get("owner")
                if not owner:
                    ident_tmp = _get_identity(interactive=False, p=p)
                    owner = ident_tmp.username if ident_tmp else None
                if not owner:
                    p("[yellow]No owner known. Use:[/yellow] git update owner/repo")
                    return True
                remote = f"https://github.com/{owner}/{repo_name}.git"
            else:
                owner, repo_name = parsed
                remote = f"https://github.com/{owner}/{repo_name}.git"

            _ensure_repo_initialized(root)
            _set_origin_remote(root, remote)
            _remember_repo(root, _parse_repo_spec(remote)[0], _parse_repo_spec(remote)[1], remote)  # safe: parse_repo_spec returns tuple

        # If still no remote, try saved mapping
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

        ident = _get_identity(interactive=False, p=p)  # don't force token for normal update
        msg = msg_arg or _auto_update_message()

        if add_paths:
            p(_commit_only_paths(root, add_paths, msg))
        else:
            p(_commit_if_needed(root, msg))

        # push
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
    # Default: Pass-through to real git for EVERYTHING else.
    # This is what gives you "normal git" power.
    # Examples:
    #   git branch -a
    #   git checkout -b test
    #   git add myfile.txt
    #   git commit -m "msg"
    #   git pull
    # --------------------------------------------------------
    args = toks[1:]  # everything after the leading "git"
    ident = _get_identity(interactive=False, p=p)

    # only use identity header automatically for github https remotes on push/fetch/clone-like commands
    # for other commands, identity doesn't matter.
    use_ident = None
    if args and args[0].lower() in ("push", "fetch", "pull", "clone"):
        remote = _get_origin_remote(root)
        if remote and remote.startswith("https://") and _is_github_remote(remote) and ident:
            use_ident = ident

    rc, out = _git_run(args, cwd=root, identity=use_ident)
    p(out)
    return True
