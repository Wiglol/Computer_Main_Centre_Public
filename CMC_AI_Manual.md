# 🧠 Computer Main Centre — AI Prompt / Instruction Manual

Copy this file into chatGPT

This document serves both as a **detailed manual for humans** and a **prompt for AI assistants (e.g., ChatGPT)** to fully understand and interact with Computer Main Centre (CMC).  
It describes every command, behavior, and input convention so that an AI can reason about CMC as if it were running it locally.

---

## 💡 Overview

Computer Main Centre (CMC) is a **local command console** written in Python that provides powerful file automation, GitHub integration, and system control.  
It’s located typically at:
```
C:/Users/<user>/Desktop/CMC/Computer_Main_Centre.py
```

CMC is **entirely offline** (no remote dependencies) and uses **safe local operations** with built-in confirmation prompts, batch automation, and macro support.

Typical workflow:
1. Launch via `Start_CMC.vbs` (auto-detects Python).  
2. Use `help` or `/gitsetup` or `/qbuild` to get started.
3. Optionally, link with a public folder like `Computer_Main_Centre_Public` for releases.

---

## 🧭 Core Behavior

- All commands are **case-insensitive**.
- All paths **must** be surrounded by single quotes `'C:/path/to/file'`.
- Commands can be **chained** using semicolons (`;`).
- Built-in variables:
  - `%DATE%` → Current date (`YYYY-MM-DD`)
  - `%NOW%` → Timestamp with time
  - `%HOME%` → User’s home folder
- Prompts are **confirmed unless Batch Mode is ON**.
- Dry-Run Mode simulates actions without executing.

Example:
```
batch on; copy 'C:/source.txt' to 'C:/dest.txt'; batch off
```

---

## 🗂 COMMAND SET SUMMARY

### 📁 Navigation & Info
```
pwd                      Show current working directory
cd 'C:/path'             Change directory
back / home              Go back or to home
list ['C:/path']         List contents
info 'path'              File/folder info
find 'term'              Search by name
findext '.ext'           Find by extension
recent ['path']          Show most recent files
biggest ['path']         Largest files/folders
search 'text'            Search inside text-like files
```

### 🧱 File Operations
```
create file 'name.txt' in 'C:/path'
create folder 'MyFolder' in 'C:/path'
write 'C:/path/file.txt' text='hello'
read 'C:/path/file.txt' [head=50]
move 'C:/src' to 'C:/dst'
copy 'C:/src' to 'C:/dst'
rename 'C:/old' to 'new'
delete 'C:/path'
zip 'C:/path' → creates C:/path.zip
unzip 'C:/file.zip' to 'C:/dest'
open 'C:/path/app.exe'
explore 'C:/path'
backup 'C:/src' 'C:/dest'  → zip into dest with timestamp
run 'C:/path/file.bat'     → supports .py, .bat, .exe, .vbs
```

The `run` command automatically detects the file type and uses:
- `.py` → Python subprocess
- `.bat`, `.cmd` → Shell
- `.vbs` → `wscript`
- `.exe` → Direct `os.startfile`
- Anything else → Open with system default

### 🌍 Internet Commands
```
download 'https://...' to 'C:/Downloads'
downloadlist 'C:/urls.txt' to 'C:/Downloads'
open url 'https://example.com'
```

### 🧰 Macros
Macros are saved command sequences stored persistently in a JSON file.

```
macro add publish = delete 'Public/CMC.py'; copy 'Main/CMC.py' to 'Public'
macro run publish
macro list
macro delete <name>
macro clear
```

They support all standard syntax including variables (`%DATE%`) and chaining (`;`).

Example advanced macro:
```
macro add autopublish = delete 'C:/Users/user/Desktop/Public/CMC.py'; copy 'C:/Users/user/Desktop/CMC/Computer_Main_Centre.py' to 'C:/Users/user/Desktop/Public'; run 'C:/Users/user/Desktop/Public/Start_CMC.vbs' in 'C:/Users/user/Desktop/Public'; sleep 3; sendkeys "macro run publish_public{ENTER}"
```

### ⚙️ Control
```
batch on | batch off        Auto-confirm prompts
dry-run on | dry-run off    Simulate without executing
ssl on | ssl off            Toggle SSL verification
status                      Show system state
log                         Show operation log
undo                        Undo last reversible op
exit                        Exit program
```

### ☕ Java Integration
```
java list                   Show installed versions
java version                Show current version
java change <8|17|21>       Switch active JDK
java reload                 Re-read system Java_HOME
```

### 🔎 Quick Path Indexing (Local API)
```
/qfind term1 term2          Fuzzy find files
/qcount                     Count indexed paths
/qbuild [C E F]             Rebuild local index
```

### 🌐 Git Commands
```
/gitsetup "RepoName"        Create + push new GitHub repo
/gitlink "URL"              Link to existing repo
/gitupdate "message"        Add → Commit → Push
/gitpull                    Pull latest
/gitstatus                  Show changes
/gitlog                     Show commits
/gitignore add pattern      Update .gitignore
/gitclean                   Remove junk (e.g., __pycache__)
/gitdoctor                  Diagnose repo issues
```

### 🧠 Automation Utilities
```
sleep <seconds>             Pause execution (for macro timing)
sendkeys "<text>{ENTER}"    Type text/keys into active window
```

Example:
```
sendkeys "macro run publish_public{ENTER}"
```

### 🖥️ Safety System
- All destructive actions require Y/N confirmation (unless batch mode).
- Dry-run previews instead of executing.
- SSL toggle allows downloads from insecure HTTPS.

---

## 🧩 Command Syntax Rules

- Always use **single quotes `'`** around file paths or arguments.
- Double quotes `"` are used **inside sendkeys** or for messages only.
- Example good syntax:
  ```
  run 'C:/Windows/System32/cmd.exe' in 'C:/Users/Public/Desktop'
  ```
- Example invalid:
  ```
  run "C:/path"  ❌ (wrong quote style)
  ```

---

## 💤 Automation Example: Auto-Publish Flow

**Goal:** Push new CMC build to GitHub public repo.

```
macro add autopublish = delete 'C:/Users/user/Desktop/Public/Computer_Main_Centre.py'; copy 'C:/Users/user/Desktop/CMC/Computer_Main_Centre.py' to 'C:/Users/user/Desktop/Public'; run 'C:/Users/user/Desktop/Public/Start_CMC.vbs' in 'C:/Users/user/Desktop/Public'; sleep 3; sendkeys "macro run publish_public{ENTER}"
```

Steps:
1. Deletes old public file.
2. Copies fresh main version.
3. Launches public console automatically.
4. Waits 3 seconds.
5. Sends macro command to push GitHub update.

---

## 🛠️ Installation (for all users)

### Requirements
- **Python 3.10+**
- **Git for Windows**
- **Windows OS**
- **Optional:** Admin privileges for system PATH changes.

### Installation
1. Install Python 3 (add to PATH).  
2. In Command Prompt:
   ```bash
   pip install rich requests pyautogui prompt_toolkit

3. (Optional) Install Git for Windows:
   https://git-scm.com/download/win

4. Launch:
   ```bash
   python Computer_Main_Centre.py
   ```
   or double-click `Start_CMC.vbs`.

---

## 🧩 Examples of Advanced Macros

### 🔁 Backup & Commit
```
macro add backup_commit = backup 'C:/Users/user/Documents' 'C:/Users/user/Backups'; /gitupdate "Auto backup %NOW%"
```

### 🚀 Server Launcher
```
macro add launch_server = batch on; echo "🧠 Launching JourneyToTheCore server..."; run 'cmd.exe /c "start "" "C:/Users/user/AppData/Roaming/ATLauncher/servers/JourneytotheCore/LaunchServer.bat""' in 'C:/Users/user/AppData/Roaming/ATLauncher/servers/JourneytotheCore'; sleep 3; echo "🌐 Starting Playit tunnel..."; run 'cmd.exe /c "start "" "C:/ProgramData/Microsoft/Windows/Start Menu/Programs/Playit.gg/Playit.gg.lnk""'; batch off; echo "✅ Both launched!"
```

---

## 🧠 AI PROMPT MODE

To use this file as an AI prompt for ChatGPT or other LLMs, simply paste it into a new chat and include:

> “You are assisting with Computer Main Centre (CMC). You fully understand this manual, its syntax, commands, and macros. Respond as if you can operate CMC locally and assist with macro creation, debugging, and automation.”

After this, ChatGPT will understand all command syntax, including:
- `'` vs `"` usage
- How macros, batch, and dry-run work
- Git, Java, and search features
- How to structure semicolon-separated commands

---

## ✅ Summary

CMC is a full local automation shell that bridges:
- File ops  
- Git ops  
- Java control  
- Download management  
- Macro automation  
- GUI interaction (via sendkeys)

It runs **entirely locally** and provides a consistent, safe command interface for power users.

