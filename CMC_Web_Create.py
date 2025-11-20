"""
CMC_Web_Create.py
------------------
AI-assisted web project generator for Computer Main Centre (CMC).

Usage (from CMC main script):
    from CMC_Web_Create import op_web_create

    if low == "webcreate":
        op_web_create()
        return

This module is self-contained and only uses the Python standard library.
It prints directly to stdout using plain print() calls.
"""

from __future__ import annotations

import os
import sys
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Optional
import shutil

def find_npm():
    """Return absolute path to npm executable, or None if not found."""
    for cmd in ["npm.cmd", "npm.exe", "npm"]:
        found = shutil.which(cmd)
        if found:
            return found
    return None



# ------------------------------------------------------------
# Small helpers
# ------------------------------------------------------------

def _cwd() -> Path:
    return Path.cwd()


def _print_header(title: str) -> None:
    print(title)
    print("-" * 60)


def _slugify(name: str) -> str:
    """Turn 'My App Name' into 'my-app-name'."""
    clean = []
    last_dash = False
    for ch in name.strip():
        if ch.isalnum():
            clean.append(ch.lower())
            last_dash = False
        elif ch in " _-":
            if not last_dash:
                clean.append("-")
                last_dash = True
        # ignore everything else
    s = "".join(clean).strip("-")
    return s or "my-web-app"


def _yes_no(prompt: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        ans = input(f"{prompt} {suffix}: ").strip().lower()
        if not ans:
            return default
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        print("Please answer y or n.")


def _choice(prompt: str, options: List[str], default: Optional[str] = None) -> str:
    opts_disp = "/".join(options)
    while True:
        if default:
            ans = input(f"{prompt} ({opts_disp}) [{default}]: ").strip().lower()
            if not ans:
                return default
        else:
            ans = input(f"{prompt} ({opts_disp}): ").strip().lower()
        if ans in options:
            return ans
        print(f"Please choose one of: {', '.join(options)}")


def _run_cmd(cmd: List[str], cwd: Path, env: Optional[Dict[str, str]] = None) -> bool:
    """Run a command, show it to the user, return True on success."""
    print()
    print(f"[cmd] (cwd={cwd})")
    print("      " + " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env or os.environ.copy(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except FileNotFoundError:
        print(f"[!] Command not found: {cmd[0]} (is it installed and on PATH?)")
        return False

    if proc.returncode != 0:
        print("[!] Command failed with exit code", proc.returncode)
        print(proc.stdout)
        return False

    out = proc.stdout or ""
    if out.strip():
        lines = out.splitlines()
        tail = lines[-20:] if len(lines) > 20 else lines
        for line in tail:
            print("   ", line)
    return True


# ------------------------------------------------------------
# Data structures
# ------------------------------------------------------------

@dataclass
class ProjectConfig:
    name: str
    folder: Path
    frontend: str   # none / vanilla / react / vue / svelte
    backend: str    # none / express / flask / fastapi


# ------------------------------------------------------------
# Frontend generation (no Vite CLI, we write the files ourselves)
# ------------------------------------------------------------

def _frontend_package_json(cfg: ProjectConfig) -> Dict:
    base_name = _slugify(cfg.name) + "-client"
    if cfg.frontend == "vanilla":
        return {
            "name": base_name,
            "version": "0.0.0",
            "private": True,
            "scripts": {
                "dev": "vite",
                "build": "vite build",
                "preview": "vite preview",
            },
            "devDependencies": {
                "vite": "^5.4.0",
            },
        }
    if cfg.frontend == "react":
        return {
            "name": base_name,
            "version": "0.0.0",
            "private": True,
            "scripts": {
                "dev": "vite",
                "build": "vite build",
                "preview": "vite preview",
            },
            "dependencies": {
                "react": "^18.0.0",
                "react-dom": "^18.0.0",
            },
            "devDependencies": {
                "vite": "^5.4.0",
                "@vitejs/plugin-react-swc": "^3.5.0",
            },
        }
    if cfg.frontend == "vue":
        return {
            "name": base_name,
            "version": "0.0.0",
            "private": True,
            "scripts": {
                "dev": "vite",
                "build": "vite build",
                "preview": "vite preview",
            },
            "dependencies": {
                "vue": "^3.5.0",
            },
            "devDependencies": {
                "vite": "^5.4.0",
                "@vitejs/plugin-vue": "^5.0.0",
            },
        }
    elif cfg.frontend == "svelte":
        return {
            "name": f"{cfg.name}-client",
            "version": "0.0.0",
            "private": True,
            "scripts": {
                "dev": "vite",
                "build": "vite build",
                "preview": "vite preview"
            },
            "devDependencies": {
                "svelte": "^5.0.0",
                "@sveltejs/vite-plugin-svelte": "^5.1.1",
                "vite": "^6.0.0"
            }
        }
    raise ValueError(f"Unsupported frontend: {cfg.frontend}")


def _write_frontend_files(cfg: ProjectConfig, client_dir: Path) -> None:
    src = client_dir / "src"
    src.mkdir(parents=True, exist_ok=True)

    index_html = client_dir / "index.html"

    # --- vanilla -------------------------------------------------
    if cfg.frontend == "vanilla":
        main_file = src / "main.js"
        index_html.write_text(
            "<!doctype html>\n"
            "<html>\n"
            "  <head>\n"
            "    <meta charset='utf-8' />\n"
            f"    <title>{cfg.name}</title>\n"
            "  </head>\n"
            "  <body>\n"
            "    <div id='app'></div>\n"
            "    <script type='module' src='/src/main.js'></script>\n"
            "  </body>\n"
            "</html>\n",
            encoding="utf-8",
        )
        main_file.write_text(
            "document.querySelector('#app').innerHTML = `\n"
            "  <h1>Hello from CMC vanilla template</h1>\n"
            "  <p>Edit src/main.js to get started.</p>\n"
            "`;\n",
            encoding="utf-8",
        )
        (client_dir / "vite.config.mjs").write_text(
            "import { defineConfig } from 'vite'\n"
            "export default defineConfig({})\n",
            encoding="utf-8",
        )
        return

    # --- React ---------------------------------------------------
    if cfg.frontend == "react":
        main_file = src / "main.jsx"
        index_html.write_text(
            "<!doctype html>\n"
            "<html>\n"
            "  <head>\n"
            "    <meta charset='utf-8' />\n"
            f"    <title>{cfg.name}</title>\n"
            "  </head>\n"
            "  <body>\n"
            "    <div id='root'></div>\n"
            "    <script type='module' src='/src/main.jsx'></script>\n"
            "  </body>\n"
            "</html>\n",
            encoding="utf-8",
        )
        main_file.write_text(
            "import React from 'react'\n"
            "import ReactDOM from 'react-dom/client'\n"
            "\n"
            "function App() {\n"
            "  return (\n"
            "    <main style={{ padding: '2rem', fontFamily: 'system-ui' }}>\n"
            "      <h1>CMC React template</h1>\n"
            "      <p>Edit src/main.jsx to get started.</p>\n"
            "    </main>\n"
            "  )\n"
            "}\n"
            "\n"
            "ReactDOM.createRoot(document.getElementById('root')).render(\n"
            "  <React.StrictMode>\n"
            "    <App />\n"
            "  </React.StrictMode>,\n"
            ")\n",
            encoding="utf-8",
        )
        (client_dir / "vite.config.mjs").write_text(
            "import { defineConfig } from 'vite'\n"
            "import react from '@vitejs/plugin-react-swc'\n"
            "\n"
            "export default defineConfig({\n"
            "  plugins: [react()],\n"
            "})\n",
            encoding="utf-8",
        )
        return

    # --- Vue -----------------------------------------------------
    if cfg.frontend == "vue":
        main_file = src / "main.js"
        app_vue = src / "App.vue"
        index_html.write_text(
            "<!doctype html>\n"
            "<html>\n"
            "  <head>\n"
            "    <meta charset='utf-8' />\n"
            f"    <title>{cfg.name}</title>\n"
            "  </head>\n"
            "  <body>\n"
            "    <div id='app'></div>\n"
            "    <script type='module' src='/src/main.js'></script>\n"
            "  </body>\n"
            "</html>\n",
            encoding="utf-8",
        )
        main_file.write_text(
            "import { createApp } from 'vue'\n"
            "import App from './App.vue'\n"
            "\n"
            "createApp(App).mount('#app')\n",
            encoding="utf-8",
        )
        app_vue.write_text(
            "<template>\n"
            "  <main style=\"padding: 2rem; font-family: system-ui\">\n"
            "    <h1>CMC Vue template</h1>\n"
            "    <p>Edit src/App.vue to get started.</p>\n"
            "  </main>\n"
            "</template>\n"
            "\n"
            "<script setup>\n"
            "// minimal setup\n"
            "</script>\n",
            encoding="utf-8",
        )
        (client_dir / "vite.config.mjs").write_text(
            "import { defineConfig } from 'vite'\n"
            "import vue from '@vitejs/plugin-vue'\n"
            "\n"
            "export default defineConfig({\n"
            "  plugins: [vue()],\n"
            "})\n",
            encoding="utf-8",
        )
        return

    # --- Svelte --------------------------------------------------
    if cfg.frontend == "svelte":
        main_file = src / "main.js"
        app_svelte = src / "App.svelte"
        index_html.write_text(
            "<!doctype html>\n"
            "<html>\n"
            "  <head>\n"
            "    <meta charset='utf-8' />\n"
            f"    <title>{cfg.name}</title>\n"
            "  </head>\n"
            "  <body>\n"
            "    <div id='app'></div>\n"
            "    <script type='module' src='/src/main.js'></script>\n"
            "  </body>\n"
            "</html>\n",
            encoding="utf-8",
        )
        main_file.write_text(
            "import App from './App.svelte'\n"
            "\n"
            "const app = new App({\n"
            "  target: document.getElementById('app'),\n"
            "})\n"
            "\n"
            "export default app\n",
            encoding="utf-8",
        )
        app_svelte.write_text(
            "<main style='padding: 2rem; font-family: system-ui'>\n"
            "  <h1>CMC Svelte template</h1>\n"
            "  <p>Edit src/App.svelte to get started.</p>\n"
            "</main>\n",
            encoding="utf-8",
        )
        (client_dir / "vite.config.mjs").write_text(
            "import { defineConfig } from 'vite'\n"
            "import { svelte } from '@sveltejs/vite-plugin-svelte'\n"
            "\n"
            "export default defineConfig({\n"
            "  plugins: [svelte()],\n"
            "})\n",
            encoding="utf-8",
        )
        return

    raise ValueError(f"Unsupported frontend: {cfg.frontend}")


def _generate_frontend(cfg: ProjectConfig) -> None:
    """
    Create the frontend folder, write package.json + starter files,
    and (when possible) run npm install for you.

    For Svelte projects we use `npm install --legacy-peer-deps`
    to avoid the current Vite/Svelte peer-dependency conflict.
    """
    if cfg.frontend == "none":
        return

    client_dir = cfg.folder / "client"

    # Don't overwrite an existing non-empty client folder
    if client_dir.exists() and any(client_dir.iterdir()):
        print(f"[webcreate] Skipping frontend: {client_dir} already exists and is not empty.")
        return

    client_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating {cfg.frontend} frontend in {client_dir} ...")

    # 1) package.json template based on framework
    pkg = _frontend_package_json(cfg)
    (client_dir / "package.json").write_text(
        json.dumps(pkg, indent=2),
        encoding="utf-8",
    )

    # 2) starter source files (App.vue / main.js / etc.)
    _write_frontend_files(cfg, client_dir)

    # 3) README for the client
    (client_dir / "README.md").write_text(
        f"# {cfg.name} – client\n\n"
        "Generated by CMC webcreate.\n\n"
        "## Getting started\n"
        "```bash\n"
        "npm install\n"
        "npm run dev\n"
        "```\n",
        encoding="utf-8",
    )

    # 4) Try to install dependencies automatically
    print("Running npm install for frontend (this may take a while)...")

    npm = find_npm()
    ok = False

    if npm:
        cmd = [npm, "install"]

        # SVELTE = special case → ignore peer-dependency conflicts
        if cfg.frontend == "svelte":
            cmd.append("--legacy-peer-deps")

        ok = _run_cmd(cmd, client_dir)
    else:
        print("[!] npm not found. You can run it manually inside client/:  npm install")
        ok = False

    if not ok:
        if cfg.frontend == "svelte":
            print(
                "[webcreate] npm install failed or reported dependency conflicts.\n"
                "           Inside client/, you can try:\n"
                "             npm install --legacy-peer-deps\n"
                "           or, if you prefer, just keep the files and adjust deps manually."
            )
        else:
            print(
                "[webcreate] npm install failed or npm not found. "
                "You can run it manually later inside client/."
            )





# ------------------------------------------------------------
# Backend generation
# ------------------------------------------------------------

def _generate_backend_flask(cfg: ProjectConfig, server_dir: Path) -> None:
    server_dir.mkdir(parents=True, exist_ok=True)
    (server_dir / "requirements.txt").write_text(
        "flask\nflask-cors\n",
        encoding="utf-8",
    )
    (server_dir / "app.py").write_text(
        "from flask import Flask, jsonify\n"
        "from flask_cors import CORS\n"
        "\n"
        "app = Flask(__name__)\n"
        "CORS(app)\n"
        "\n"
        "@app.get('/api/hello')\n"
        "def hello():\n"
        "    return jsonify({'message': 'Hello from Flask backend'})\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    app.run(debug=True)\n",
        encoding="utf-8",
    )
    (server_dir / "start_server.bat").write_text(
        "@echo off\n"
        "cd /d %~dp0\n"
        "call venv\\Scripts\\activate.bat\n"
        "python app.py\n",
        encoding="utf-8",
    )
    (server_dir / ".gitignore").write_text(
        "venv/\n__pycache__/\n*.pyc\n",
        encoding="utf-8",
    )

    print("Creating Python virtual environment for Flask backend...")
    python_exe = sys.executable or "python"
    _run_cmd([python_exe, "-m", "venv", "venv"], server_dir)
    print("Installing backend dependencies with pip...")
    _run_cmd([str(server_dir / "venv" / "Scripts" / "pip.exe"), "install", "-r", "requirements.txt"], server_dir)


def _generate_backend_fastapi(cfg: ProjectConfig, server_dir: Path) -> None:
    server_dir.mkdir(parents=True, exist_ok=True)
    (server_dir / "requirements.txt").write_text(
        "fastapi\nuvicorn[standard]\n",
        encoding="utf-8",
    )
    (server_dir / "app.py").write_text(
        "from fastapi import FastAPI\n"
        "from fastapi.middleware.cors import CORSMiddleware\n"
        "\n"
        "app = FastAPI()\n"
        "app.add_middleware(\n"
        "    CORSMiddleware,\n"
        "    allow_origins=['*'],\n"
        "    allow_methods=['*'],\n"
        "    allow_headers=['*'],\n"
        ")\n"
        "\n"
        "@app.get('/api/hello')\n"
        "async def hello():\n"
        "    return {'message': 'Hello from FastAPI backend'}\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    import uvicorn\n"
        "    uvicorn.run('app:app', reload=True)\n",
        encoding="utf-8",
    )
    (server_dir / "start_server.bat").write_text(
        "@echo off\n"
        "cd /d %~dp0\n"
        "call venv\\Scripts\\activate.bat\n"
        "python app.py\n",
        encoding="utf-8",
    )
    (server_dir / ".gitignore").write_text(
        "venv/\n__pycache__/\n*.pyc\n",
        encoding="utf-8",
    )

    print("Creating Python virtual environment for FastAPI backend...")
    python_exe = sys.executable or "python"
    _run_cmd([python_exe, "-m", "venv", "venv"], server_dir)
    print("Installing backend dependencies with pip...")
    _run_cmd([str(server_dir / "venv" / "Scripts" / "pip.exe"), "install", "-r", "requirements.txt"], server_dir)


def _generate_backend_express(cfg: ProjectConfig, server_dir: Path) -> None:
    server_dir.mkdir(parents=True, exist_ok=True)
    (server_dir / "server.js").write_text(
        "const express = require('express');\n"
        "const cors = require('cors');\n"
        "\n"
        "const app = express();\n"
        "const port = process.env.PORT || 5000;\n"
        "\n"
        "app.use(cors());\n"
        "\n"
        "app.get('/api/hello', (req, res) => {\n"
        "  res.json({ message: 'Hello from Express backend' });\n"
        "});\n"
        "\n"
        "app.listen(port, () => {\n"
        "  console.log(`Server listening on http://localhost:${port}`);\n"
        "});\n",
        encoding="utf-8",
    )
    (server_dir / "package.json").write_text(
        json.dumps(
            {
                "name": _slugify(cfg.name) + "-server",
                "version": "0.0.0",
                "private": True,
                "scripts": {
                    "start": "node server.js"
                },
                "dependencies": {
                    "express": "^4.19.0",
                    "cors": "^2.8.5"
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (server_dir / ".gitignore").write_text(
        "node_modules/\n",
        encoding="utf-8",
    )
    (server_dir / "start_server.bat").write_text(
        "@echo off\n"
        "cd /d %~dp0\n"
        "npm start\n",
        encoding="utf-8",
    )

    print("Installing Express backend dependencies with npm...")
    ok = _run_cmd(["npm", "install"], server_dir)
    if not ok:
        print("[webcreate] npm install failed for Express backend. Run it manually in server/ later.")


def _generate_backend(cfg: ProjectConfig) -> None:
    if cfg.backend == "none":
        return

    server_dir = cfg.folder / "server"

    if server_dir.exists() and any(server_dir.iterdir()):
        print(f"[webcreate] Skipping backend: {server_dir} already exists and is not empty.")
        return

    if cfg.backend == "flask":
        _generate_backend_flask(cfg, server_dir)
    elif cfg.backend == "fastapi":
        _generate_backend_fastapi(cfg, server_dir)
    elif cfg.backend == "express":
        _generate_backend_express(cfg, server_dir)
    else:
        raise ValueError(f"Unsupported backend: {cfg.backend}")


# ------------------------------------------------------------
# Top-level orchestrator
# ------------------------------------------------------------


def _write_launcher(cfg: ProjectConfig) -> None:
    """Create a universal launcher that starts frontend + backend."""
    launcher_path = cfg.folder / "start_app.bat"

    lines = [
        "@echo off",
        "setlocal",
        "",
        "echo Starting backend (if available)...",
        "IF EXIST server\\venv\\Scripts\\python.exe (",
        "    start cmd /k \"cd server && venv\\Scripts\\python.exe app.py\"",
        ") ELSE IF EXIST server\\package.json (",
        "    start cmd /k \"cd server && npm start\"",
        ") ELSE (",
        "    echo No backend found.",
        ")",
        "",
        "echo Starting frontend (if available)...",
        "IF EXIST client\\package.json (",
        "    start cmd /k \"cd client && npm run dev\"",
        ") ELSE (",
        "    echo No frontend found.",
        ")",
        "",
        "echo Done!",
        "pause",
        ""
    ]

    launcher_path.write_text("\n".join(lines), encoding="utf-8")


def op_web_create() -> None:
    """Interactive entry point for CMC."""
    _print_header("CMC Web Create Wizard")

    # 1) Basic questions
    default_name = "My Web App"
    name = input(f"Project name [{default_name}]: ").strip() or default_name
    suggested_folder = _cwd() / _slugify(name)
    folder_input = input(f"Target folder [{suggested_folder}]: ").strip()
    if folder_input:
        folder = Path(folder_input).expanduser()
    else:
        folder = suggested_folder

    frontend = _choice(
        "Choose frontend",
        ["none", "vanilla", "react", "vue", "svelte"],
        default="vanilla",
    )
    backend = _choice(
        "Choose backend",
        ["none", "express", "flask", "fastapi"],
        default="none",
    )

    cfg = ProjectConfig(
        name=name,
        folder=folder,
        frontend=frontend,
        backend=backend,
    )

    print("-" * 60)
    print("Summary:")
    print(f"  Project:  {cfg.name}")
    print(f"  Folder:   {cfg.folder}")
    print(f"  Frontend: {cfg.frontend}")
    print(f"  Backend:  {cfg.backend}")
    print("-" * 60)

    if not _yes_no("Proceed and generate project structure?", True):
        print("Aborted.")
        return

    # 2) Create base folder
    cfg.folder.mkdir(parents=True, exist_ok=True)

    # 3) Generate parts
    if cfg.frontend != "none":
        _generate_frontend(cfg)
    if cfg.backend != "none":
        _generate_backend(cfg)
        
    # 4) Launcher (always created)
    _write_launcher(cfg)

    # 4) Root README
    (cfg.folder / "README.md").write_text(
        f"# {cfg.name}\n\n"
        "Generated by CMC webcreate.\n\n"
        "## Structure\n"
        "* `client/` – frontend (if chosen)\n"
        "* `server/` – backend (if chosen)\n"
        "\n"
        "You can run `websetup` later inside client/ or server/ to refine the setup.\n",
        encoding="utf-8",
    )

    print()
    print("-" * 60)
    print("Done!")
    print("You can now open the project folder and start hacking.")
    print("Tip: run 'websetup' inside client/ or server/ later to refine the setup.")
    print("-" * 60)


if __name__ == "__main__":
    op_web_create()
