# 🧠 Computer Main Centre (CMC) — AI Manual (Updated 2025-11-02)

Computer Main Centre (CMC) provides an advanced local command console with persistent macros, aliases, path indexing, Java management, and rich UI.

---

## ⚙️ Installation

### Requirements
```bash
pip install rich requests pyautogui prompt_toolkit
```
*(Optional: `pip install pyreadline3` for legacy CMD tab support.)*

---

## 🧩 Features Overview

- Safe file operations (create/read/write/move/copy/delete/zip/unzip/backup)
- Batch / Dry-Run / SSL toggle modes
- Macros with persistent storage
- Alias command shortcuts
- Java auto-detection & switching
- GitHub integration
- Quick Path Index (/qbuild, /qfind, /qcount)
- Web search integration (Google, YouTube)
- Prompt_toolkit autocompletion (TAB support)

---

## 🗂 File Operations

```bash
create file 'test.txt' in '.' with text='Hello'
create folder 'MyFolder' in 'C:/Users/Wiggo/Desktop'
read 'test.txt'
delete 'test.txt'
zip 'C:/Users/Wiggo/Desktop/MyFolder'
backup 'C:/Users/Wiggo/Desktop/Test' 'C:/Backups'
```

These commands now fully respect CMC’s **virtual working directory** (`cd` target).

---

## 🧠 Macro & Alias System

### Macros
```bash
macro add autopublish = delete 'C:/Public/CMC.py' ; copy 'C:/CMC/CMC.py' to 'C:/Public' ; run 'Start_CMC.vbs'
macro run autopublish
macro list
macro delete autopublish
```

### Aliases
```bash
alias add yt youtube
alias add ap macro run autopublish
alias list
alias delete yt
```

Aliases are saved in `%USERPROFILE%\.ai_helper\aliases.json`.

---

## ☕ Java Management

Java versions are now **automatically detected** from the system registry and common installation folders.

```bash
java list
java change jdk-17.0.16.8-hotspot
java change "C:/Program Files/Java/jdk-21"
java version
java reload
```

You can switch by **version name** or **exact path**.

---

## 🌍 Internet Commands

```bash
open url 'https://example.com'
download 'https://...' to 'C:/Downloads'
search web <query>
youtube <query>
```

- Opens results in your **default browser** (supports Brave).

---

## 🔍 Quick Path Index

```bash
/qbuild
/qcount
/qfind <query> [limit]
```

`/qbuild` now automatically indexes all drives (C, D, E, F).
Indexed data is stored locally in `paths.db`.

---

## 🧠 Autocompletion

CMC uses `prompt_toolkit` for live autocompletion of commands and paths.  
- Press **TAB** to complete commands.  
- Arrow keys to navigate suggestions.  

---

## 🧾 Notes

- All commands are case-insensitive.
- Virtual working directory respected by all search/find functions.
- Logs and macros persist between sessions.
- Rich interface auto-wraps panels and adapts to terminal width.

---

Developed by **Wiggo** — Computer Main Centre Project  
Updated: **2025-11-02**
