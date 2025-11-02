=====================================================
Computer Main Centre (CMC)
Local AI Command Console
=====================================================

Computer Main Centre (CMC) is a local AI-assisted command console for Windows designed for file automation, macros, Git management, Java control, and safe operation modes.

=====================================================
Installation
=====================================================

1. Install Python 3.11 or newer from https://www.python.org/downloads/

2. Open CMD and install required packages:

   pip install rich requests pyautogui prompt_toolkit

   (Optional: For old Windows CMD versions, also run `pip install pyreadline3`)

3. Download or clone CMC, then start with:

   cd C:\Users\<YourName>\Desktop\CMC
   py Computer_Main_Centre.py

=====================================================
Features
=====================================================

- Rich colored console interface
- Full file management (create/read/write/move/copy/delete/zip/unzip/open/explore/backup)
- Safe modes: Dry-Run and Batch
- SSL toggle for safe downloads
- Persistent macros with support for variables
- Aliases for quick command shortcuts
- GitHub integration (/gitsetup, /gitupdate, /gitpull, /gitlog, etc.)
- Java version auto-detection and management
- Quick Path Index for instant file search
- Web search integration (`search web`, `youtube`)
- Autocompletion using prompt_toolkit (press TAB)

=====================================================
Main Commands
=====================================================

NAVIGATION
  pwd / cd / back / home

FILE OPS
  create file 'name.txt' in 'C:/path' [with text='hello']
  create folder 'Name' in 'C:/path'
  read / write / copy / move / rename / delete
  zip / unzip / backup / open / explore

CONTROL
  batch on/off
  dry-run on/off
  ssl on/off
  status / log / undo / help / exit

MACROS
  macro add <name> = <commands>
  macro run <name>
  macro list / macro delete <name> / macro clear

ALIASES
  alias add <shortcut> <command>
  alias list
  alias delete <shortcut>

INTERNET
  download 'https://...' to 'C:/Downloads'
  downloadlist 'C:/urls.txt' to 'C:/Downloads'
  open url 'https://example.com'
  search web <query>
  youtube <query>

JAVA
  java list
      → Auto-detects all installed JDK/JRE versions.
  java change <path|version>
      → Change Java version system-wide or per path.
  java version
      → Shows active version and path.
  java reload
      → Reload environment from registry.

INDEXING
  /qbuild [drives]
      → Rebuild search index for all drives (auto-detects C, D, E, F).
  /qcount
      → Show indexed path count.
  /qfind <query> [limit]
      → Search indexed database.

=====================================================
Notes
=====================================================

- All commands are case-insensitive.
- CMC uses a virtual CWD (its own working directory system).
- Use quotes around paths with spaces.
- Macros saved under: %USERPROFILE%\.ai_helper\macros.json
- Aliases saved under: %USERPROFILE%\.ai_helper\aliases.json
