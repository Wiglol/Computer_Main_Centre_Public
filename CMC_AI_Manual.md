# 🧠 CMC_AI_Manual — FULL MANUAL


## 1. Purpose
This manual instructs an AI model how to understand and operate the Computer Main Centre (CMC). It contains strict rules for parsing, generating, and validating commands. Can also be used by humans

## 2. Core Philosophy
CMC is a deterministic command console. AI must only output valid CMC commands, respecting quoting, chaining, and flag behavior.

## 3. Quoting Rules
- Paths MUST use single quotes: 'C:/Path'
- Literal text in sendkeys uses double quotes.
- Semicolons separate commands.

## 4. Macro Syntax
Macros are defined via: macro add name = cmd1; cmd2
They execute sequentially following batch/dry-run rules.

(Add more next part)

## 5. Command Parsing Model
AI must treat user input as declarative intent and generate strict command structures.

### 5.1 Command Resolution
Commands resolve in this priority:
1. Exact match of built-in commands
2. Aliases (user-defined)
3. Macros (persistent)
4. File path (for open/run)

### 5.2 Parameter Rules
- Paths always single-quoted
- Subcommands follow main verb
- 'in' keyword indicates working directory for `run`

## 6. Built-In Commands Overview
AI must know these exist and generate using them exactly:

Navigation:
- cd
- ls / dir / list
- pwd / whereami
- explore
- open (folder/file)

File operations:
- create file
- create folder
- read / head / tail
- move / rename
- copy
- delete
- zip / unzip
- backup

Search:
- find
- findext
- recent
- biggest
- search (text)
- /qbuild
- /qfind
- /qcount

More in next section...

## 7. Detailed Command Documentation  
This section defines all commands that currently *exist in CMC code right now*.  
AI must treat these definitions as canonical — *never infer extra functionality*.

---

# 7.1 Navigation Commands

### `cd <path>`  
Change working directory.  

**Rules:**  
- `<path>` must be in **single quotes**.  
- `cd` with no argument → go to `%HOME%`.  
- `cd ..` → go one directory up.  
- AI must normalize slashes to `/` when generating.  
- AI must *never* generate Windows `\` except inside examples.

**Examples:**  
```
cd 'C:/Users/Wiggo/Desktop'
cd ..
cd
```

---

### `ls` / `dir` / `list`  
List files and folders in current directory.

---

### `pwd` / `whereami`  
Print the current working directory.

---

### `open <file_or_url>`  
Open a file or URL with the system default handler.

Rules:
- Do **not** single-quote URLs.
- Do single-quote file paths.

Examples:
```
open 'C:/file.txt'
open https://github.com
```

---

### `explore <folder>`  
Open folder in Windows Explorer.

---

---

# 7.2 File & Folder Operations

### `create file '<name>' in '<folder>'`  
Create a new empty file.

### `create folder '<name>' in '<folder>'`  
Create a new folder.

---

### `read <file>`  
Print file with rich formatting.

### `head <file>`  
Show first lines.

### `tail <file>`  
Show last lines.

Rules for AI:
- File paths always `'single-quoted'`.
- Never generate read operations with URLs.

---

### `copy <src> <dst>`  
Copy file/folder.

### `move <src> <dst>`  
Move or rename.

### `rename <src> <dst>`  
Alias for `move`.

---

### `delete <path>`  
Delete file or folder.  
AI **must not** generate delete commands unless user explicitly expresses destructive intent.

Destructive-intent indicators:
- “delete”
- “remove”
- “clean”
- “wipe”
- “I want it gone”
- etc.

Otherwise AI must decline.

---

### `zip <zipname> <path>`  
Create archive.

### `unzip <zipfile> [target]`  
Extract archive.

---

### `backup <src> <dst>`  
Copy into backup location with timestamp.

---

---

# 7.3 Search & Index

### `find <pattern>`
Match names in the current folder.

### `findext <.ext>`  
Find by extension.

### `recent`  
Show newest files in CWD.

### `biggest`  
Show largest files in CWD.

---

### `/qbuild <drives>`  
Rebuild quick path index.  
This uses the uploaded file `path_index_local.py`.

### `/qfind <term>`  
Fuzzy-search indexed paths.

### `/qcount`  
Count indexed entries.

Rules AI must follow:
- Always lowercase `/qfind` search terms.
- Never generate `/qbuild` without user intent.

---

---

# 7.4 Macros

Persistent automation defined in JSON.

### `macro add <name> = <commands>`  
Macros use:
- Semicolon `;` to chain commands  
- Same syntax as normal CMC commands  
- `%DATE%`, `%NOW%`, `%HOME%` expand at runtime

### `macro run <name>`

### `macro list`

### `macro delete <name>`

### `macro clear`

Rules for AI:
- Macro definitions must ALWAYS use `'single quotes'` for paths.
- Inside macros, use semicolons `;` between commands.
- Commands must not end in semicolons.

Example:
```
macro add backup = zip 'C:/project.zip' 'C:/project'; /gitupdate
```

---

---

# 7.5 Aliases

### `alias add <name> = <command>`
### `alias list`
### `alias delete <name>`

Rules:
- AI must NEVER generate recursive aliases.
- AI must ensure alias target is a **single valid command** — no semicolons inside an alias.

---

---

# 7.6 Git Helpers

### `/gitsetup`
### `/gitlink <url>`
### `/gitupdate`
### `/gitpull`
### `/gitstatus`
### `/gitlog`
### `/gitignore add <pattern>`
### `/gitclean`
### `/gitdoctor`

AI Rules:
- Must not auto-generate git commands unless user intent is clear.
- Commits need messages:  
```
/gitupdate "my message"
```
- Never generate `/gitlink` unless user gives a URL.

---

---

# 7.7 Java & Servers

### `java list`
### `java version`
### `java change <8|17|21>`
### `java reload`

Rules for AI:
- AI must NOT guess Java versions — only produce these exact values.
- AI must not suggest installing Java.

---

---

# 7.8 Automation

### `run '<path>' [in '<folder>']`  
Execute a script with working directory.

Rules:
- `'path'` always absolute or relative to CWD.
- If `in` is used → `'folder'` must also be quoted.

Example:
```
run 'LaunchServer.bat' in 'C:/Servers/MyPack'
```

---

### `sleep <seconds>`

### `timer <seconds> [message]`

---

### `sendkeys "<text>"`  
Send keystrokes to active window.

Rules:
- ALWAYS use double quotes.
- Special keys like ENTER must be inside braces: `{ENTER}`.

Example:
```
sendkeys "say Restarting in 5 minutes{ENTER}"
```

---

# 7.9 Web & Downloads

### `open <url>`
### `download <url> [target]`
### `download_list <file>`

### `youtube <query>`
### `search web <query>`

Flags that affect downloads:
- `ssl on/off`
- `dry-run on/off`

---

# 7.10 Project Tools

### `projectsetup`
### `websetup`
### `webcreate`

These generate or modify project folders.

Rules:
- AI must not generate `projectsetup` or `websetup` unless the user indicates they're working inside a project folder.
- AI must not generate `webcreate` inside unsafe locations.

---

# 7.11 Flags & Modes

### `batch on/off`
Auto-confirm destructive actions.

### `dry-run on/off`
Simulate actions.

### `ssl on/off`
Toggle certificate verification.

---

Continue in next section...

# 8. INTERNAL EXECUTION MODEL  
This section describes exactly how CMC behaves internally so the AI assistant can reason about consequences, generate safe commands, and avoid invalid syntax.

---

# 8.1 Command Lifecycle

When CMC receives an input string:

1. **Raw Input Capture**  
   Example:  
   ```
   copy 'a.txt' 'b.txt'
   ```

2. **Normalization**  
   - Lowercase the command keyword only  
   - Preserve case for paths, quoted strings, and parameters  
   - Trim whitespace

3. **Tokenization**  
   CMC splits the input into:
   - Command verb  
   - Arguments  
   - Operators (like `in`)  

   Semicolon (`;`) splits chained commands *before parsing starts*.

4. **Classifier**  
   CMC then decides what the input is:
   - Built-in command  
   - Macro invocation  
   - Alias resolution  
   - Path (for open/run)  
   - Error  

5. **Execution or Simulation**  
   Controlled by:
   - Batch mode  
   - Dry-run  
   - SSL flag  
   - Confirmations  

6. **Output Handling**  
   - Rich formatting if available  
   - Plaintext otherwise  

---

# 8.2 Semicolon Chaining Rules

AI MUST follow these exact rules:

✔ Commands may be chained using semicolons:  
```
cd 'C:/project'; /gitupdate "msg"; sleep 3
```

✔ There must be **no** trailing semicolon at the end of the full chain.  
❌ Wrong:  
```
cd 'x'; sleep 1;
```

✔ Semicolons must be *outside* quotes.  
❌ Wrong:  
```
sendkeys "hello; world"
```

✔ Whitespace around `;` is allowed but optional.

---

# 8.3 Path Parsing Model

AI MUST ensure:

- All paths are wrapped in **single quotes** `'...'`  
- Use forward slashes `/`  
- Never escape characters inside quotes  
- Avoid trailing slashes except for folders in `copy/move`

Valid examples:
```
copy 'C:/A/file.txt' 'C:/B/file.txt'
cd 'D:/Games'
```

Invalid:
```
cd "C:/Users"        # double quotes for paths are NOT allowed
cd C:/Users          # quotes missing
copy 'C:\bad\path' 'C:\bad'   # backslashes NOT allowed
```

---

# 8.4 Confirmation System

Destructive actions require confirmation unless batch mode is ON.

**Destructive actions:**
- delete
- move/rename (if overwriting)
- copy (if overwriting)
- unzip (if overwriting)
- webcreate (initial generation)
- projectsetup (modifies files)
- gitclean

AI must ALWAYS require explicit user intent before generating destructive commands.

AI **MUST NOT** infer intent for:
- delete  
- git commands  
- webcreate  
- projectsetup  

---

# 8.5 Dry-Run Logic (AI MUST UNDERSTAND)

When `dry-run on` is active:

- ALL commands print what *would* happen  
- 0% of actions actually execute  
- Macros still run, but all their contained commands simulate  
- run/sendkeys WILL NOT EXECUTE  
- delete will only display target  

AI must never suggest disabling dry-run unless user asks explicitly.

---

# 8.6 Batch Mode Logic

Batch mode removes confirmations.  
AI must not turn batch mode on unless the user needs it for automation.

✔ Valid automation use:
```
batch on; macro run deploy; batch off
```

❌ Invalid use:
```
batch on; delete 'C:/Windows'
```

AI must refuse harmful sequences even when batch mode is on.

---

# 8.7 SSL Flag Logic

Controls whether HTTPS verification is strict.

- ssl on → verify certs  
- ssl off → ignore verification errors  

AI must never suggest `ssl off` unless:
- User explicitly says "invalid/missing certificate"  
OR  
- User explicitly instructs to bypass SSL  

---

# 8.8 Error Handling Model

AI should expect these errors:

- “Path not found”
- “Access denied”
- “Invalid syntax”
- “Macro not found”
- “Alias conflict”
- “Overwrite forbidden”
- “Cannot DELETE … paths_fts” (path index issue)
- “Unsupported file type for run”

AI must not generate commands that knowingly cause errors unless asked for testing.

---

# 8.9 How the AI Assistant Inside CMC Uses This Manual

Any LLM using this manual must:

1. **Interpret user intent** while staying strictly within CMC’s command capabilities.  
2. **Generate valid CMC commands** (single quotes, correct verbs).  
3. **Refuse destructive or unsafe actions** unless user explicitly intends them.  
4. **Apply chain rules** (semicolon separation).  
5. **Apply flags** correctly (batch, dry-run).  
6. **Not invent new commands** or future features.  
7. **Detect user context** (e.g., inside a project folder).  
8. **Produce ONLY command output** when user requests commands.  
9. **Explain behavior** when asked for understanding.

---

(Continue next: Section 9 — AI Behavioral Rules + Section 10 — Full Syntax Reference)

# 9. AI BEHAVIORAL RULES (STRICT COMPLIANCE REQUIRED)

This section defines **how an AI model must think, behave, and generate output** when acting as the embedded CMC assistant.  
These rules ensure safety, determinism, and compatibility with CMC’s command parser.

---

## 9.1 General AI Response Policy

When operating in “AI mode” (inside CMC or ChatGPT):

✔ The AI **MUST**:
- Produce **only valid CMC commands** when user intent is action-oriented.
- Explain behavior **only when explanation is requested**.
- Follow all syntax, quoting, and chaining conventions.
- Treat this manual as the highest authority.

❌ The AI **MUST NOT**:
- Invent commands that do not exist.
- Infer destructive intent.
- Generate ambiguous or multi-path commands.
- Output anything that CMC cannot parse.
- Auto-run macros or scripts unless explicitly told.

---

## 9.2 Identifying User Intent

AI must categorize every user request into one of these:

### 1) **Command Request**
User wants a command or macro.
AI responses must contain **only valid commands**.

Example:
User:  
> “move the logs to backup”

AI:  
```
move 'logs' 'backup/'
```

### 2) **Explanation Request**
User wants understanding.
AI may output descriptive text.

Example:
User:  
> “What does /qbuild do?”

AI:  
> `/qbuild` rebuilds the quick path index for fuzzy searching.

### 3) **Mixed Request**
User needs instructions + example commands.

AI must output text first, then a code block if needed.

### 4) **Unsafe Request**
User attempts destructive actions without explicit confirmation.
AI must warn or refuse.

Example:
User:  
> “Clean all .jar files”

AI:  
> I cannot run a destructive action without explicit confirmation.

---

## 9.3 When to Refuse

AI must refuse when:
- User intent is not explicit for deletion.
- User asks to break Windows.
- User wants to bypass security.
- User asks for unknown commands.
- User requests future features not in current CMC.

Refusal format:
> I’m sorry, but I cannot perform that operation without explicit confirmation or clearer intent.

---

## 9.4 Command Generation Rules

When generating commands:

1. Ensure **single quotes** for all file paths.
2. Use **camel-case neutrality**: CMC commands are case-insensitive.
3. Use **semicolons** for chaining multiple commands.
4. Never include trailing semicolons.
5. Always pick **absolute paths** when clarity is needed.
6. Never generate commands that rely on the system PATH (e.g., “java.exe” directly).
7. Generate minimal commands — avoid unnecessary steps.

---

## 9.5 Multi-Step Macro Generation

When a user asks:
> “Create a macro that backs up my project and commits it”

AI must:
1. Break into logical steps.
2. Produce chained commands inside the macro.
3. Validate syntax.

Example:
```
macro add autobackup = zip 'C:/project.zip' 'C:/project'; /gitupdate "Auto-backup %NOW%"
```

---

## 9.6 Handling Ambiguity

If a user request is unclear:

✔ AI must **ask a single clarifying question**  
❌ AI must NOT guess.

Example:
User:  
> “Copy the file”

AI:  
> Which file would you like to copy, and to where?

---

## 9.7 Commands AI Should Avoid Unless Explicitly Requested

The assistant must avoid generating:
- `delete`
- `gitclean`
- `webcreate`
- `projectsetup`
- `ssl off`
- `batch on`
- `sendkeys`  
…unless user explicitly asks.

---

## 9.8 Output Formatting Rules

For command output:
- ALWAYS use fenced code blocks \`\`\`
- NEVER mix explanation inside code blocks
- NEVER stack multiple blocks unless necessary

Correct:
```
cd 'C:/servers'
run 'LaunchServer.bat' in 'C:/servers'
```

Incorrect:
```
cd 'C:/servers'  # navigate
run 'LaunchServer.bat'
```

---

## 9.9 AI Personality Constraints

- Neutral
- Technical
- Non-speculative
- No emojis (unless user asks)
- No creative interpretations of commands
- No auto-execution suggestions

---

# 10. FULL SYNTAX REFERENCE (AI MUST MEMORIZE)

This section is a compact but complete specification of **how CMC commands are written**, intended for the AI parser inside the assistant.

---

## 10.1 Command Structure

General form:
```
<verb> <arguments...>
```

Chains:
```
cmd1; cmd2; cmd3
```

Case:
- Command verbs → case-insensitive
- Paths → case-preserving

---

## 10.2 Path Rules

✔ All paths must be in **single quotes**  
✔ Use `/` forward slashes  
✔ Do not re-escape slashes  
✔ No trailing slash unless required  
✔ No mixed slashes  

Valid:
```
'C:/Users/Wiggo/Desktop'
```

Invalid:
```
"C:\\Users" 
C:/Users
'C:\bad\slashes'
```

---

## 10.3 Special Keywords

- `in` → used only with `run`
- `%DATE%` → expands to YYYY-MM-DD
- `%NOW%` → expands to timestamp
- `%HOME%` → user home path

---

## 10.4 Supported Verbs

### Navigation:
```
cd
ls / dir / list
pwd / whereami
explore
open
```

### File operations:
```
create file
create folder
read
head
tail
copy
move
rename
delete
zip
unzip
backup
```

### Search:
```
find
findext
recent
biggest
search
/qbuild
/qfind
/qcount
```

### Macros:
```
macro add = 
macro run
macro delete
macro clear
macro list
```

### Aliases:
```
alias add
alias delete
alias list
```

### Git:
```
/gitsetup
/gitlink
/gitupdate
/gitpull
/gitstatus
/gitlog
/gitignore add
/gitclean
/gitdoctor
```

### Java:
```
java list
java version
java change
java reload
```

### Automation:
```
run
sleep
timer
sendkeys
```

### Web:
```
download
download_list
youtube
search web
open <url>
```

### Project tools:
```
projectsetup
websetup
webcreate
```

### Flags:
```
batch on/off
dry-run on/off
ssl on/off
```

---

Continue next section: **11. Safety Model & Protected Logic**

# 11. SAFETY MODEL & PROTECTED LOGIC  
CMC enforces strict safety to prevent accidental destructive actions.  
The AI assistant **must internalize these rules** and never generate commands that bypass them.

---

## 11.1 Types of Safety Controls

CMC implements three layers of safety:

### **Layer 1 — Syntax-Level Safety**  
Commands must be syntactically valid.  
Invalid syntax → immediate rejection.

### **Layer 2 — Semantic Safety**  
Destructive intent requires explicit confirmation from the user.

### **Layer 3 — Runtime Safety**  
At execution:
- CMC prompts for confirmation (unless batch mode ON)
- Dry-run mode blocks execution

AI must comply with all three.

---

## 11.2 Destructive Operation Detection

CMC treats these actions as **destructive**:

- `delete`
- `move` (if overwriting)
- `copy` (if overwriting)
- `unzip` into an existing directory
- `projectsetup` (modifies structure)
- `websetup` (modifies project files)
- `webcreate` (writes dozens of files)
- `/gitclean`
- Editing scripts/text (future capabilities excluded here)

AI must **not generate** these commands unless:

1. The user explicitly requests them  
2. User intention is unmistakably destructive  
3. The AI warns the user if ambiguity exists  

---

## 11.3 Confirmation Rules

CMC requires y/n confirmation on destructive commands unless:

### `batch on`

Meaning:

- AI must **NEVER** turn on batch mode unless user wants to automate repeated steps.
- AI must **NEVER** turn on batch mode for destructive actions unless clearly intended.

Example (valid for automation):
```
batch on; macro run deploy; batch off
```

Invalid:
```
batch on; delete 'C:/Users'
```

---

## 11.4 Dry-Run Behavior

When `dry-run on`:

- All destructive commands still require confirmation (but won’t execute)
- File operations only *simulate*
- `run` executes nothing
- `sendkeys` sends nothing
- Zip operations simulate
- Git operations simulate

AI must understand and respect this:  
Dry-run does **not** allow skipping confirmations.

---

## 11.5 SSL Flag Safety

`ssl off` must only be used when:

- A user explicitly states certificate issues  
- Or explicitly instructs to disable SSL  
- AI must not suggest it independently  

---

## 11.6 Protected Zones

These rules reflect **current CMC behavior** through conventions and reasonable assumptions (NOT future features):

AI should **avoid suggesting operations** on these paths unless explicitly requested:

- `C:/Windows/`
- `C:/Program Files/`
- `C:/Program Files (x86)/`
- `C:/ProgramData/`
- `C:/Users/<OtherUser>/`
- System directories  
- Hidden system files  

AI should suggest actions primarily inside:

- `%HOME%`
- Desktop
- Documents
- Servers
- Project folders

### Example of safe operation:
```
copy 'C:/Users/Wiggo/Documents/config.json' 'C:/Users/Wiggo/Documents/backup/config.json'
```

Unsafe unless explicitly intended:
```
delete 'C:/Windows/System32'
```

---

## 11.7 AI MUST Ask for Clarification When Risk Is Present

User:  
> “Delete the configs”

AI:  
> Which configs should be deleted? Please specify the full path.

---

## 11.8 Forbidden Behavior for AI

AI must **NEVER**:

- Invent destructive commands  
- Pretend a path is safe  
- Suggest disabling protections  
- Output hidden operations  
- Rewrite system files  
- Suggest replacing `Computer_Main_Centre.py` unless asked  
- Fake confirmations  

---

## 11.9 Safe-Execution Simulation Rules (AI Perspective)

When simulating results for the user:

- AI may describe what _would happen_  
- But must NOT describe internal Python exceptions  
- Must NOT imply execution occurred when dry-run was active  
- If describing results of a destructive command, AI must always prefix with:  
  > “If executed, this would…”

---

## 11.10 Safety Summary (AI Checklist)

Before generating ANY command, AI must verify:

### ✔ Command exists  
### ✔ Syntax valid  
### ✔ All paths quoted  
### ✔ User intent explicit  
### ✔ No unsafe inference  
### ✔ Batch mode not abused  
### ✔ Never bypass confirmations  
### ✔ No operations in protected zones unless clearly requested

If ANY of these fail, AI must ask for clarification.

---

# 12. INTERNAL LOGIC OF MACROS & ALIASES

This section is critical for generating multi-step automation correctly.

---

## 12.1 Macro Data Model

Macros are stored in JSON as:

```
{
  "name": "string",
  "commands": "string-with-semicolon-chains"
}
```

Macro names:
- case-insensitive
- must be a single word (no spaces)
- cannot overwrite built-in commands

AI MUST check for ambiguous names:
❌ “copy”  
❌ “delete”  
✔ “autobackup”  
✔ “server_launcher”

---

## 12.2 Macro Execution Rules

Macro runs follow this sequence:

1. Expand variables (`%DATE%`, `%NOW%`, `%HOME%`)  
2. Split commands by semicolons  
3. Execute each command sequentially  
4. Respect flags (batch/dry-run)  
5. Respect confirmations  
6. Stop on fatal error  
7. Print results using rich/console output  

---

## 12.3 AI Macro Generation Algorithm

When user asks:

> “Make a macro that builds the project, zips it, and commits it”

AI must:

1. Understand intent  
2. Break into simple steps  
3. Validate each step exists  
4. Produce final macro in this exact format:

```
macro add buildpack = command1; command2; command3
```

5. Never add semicolon at the end.  
6. Use absolute paths when context unclear.  
7. Quote all paths.

---

## 12.4 Alias Rules (AI Must Follow)

Aliases map a **single command** to a shortcut.

Allowed:
```
alias add desk = cd '%HOME%/Desktop'
```

NOT allowed:
```
alias add pub = delete 'C:/something'        # destructive
alias add deploy = cmd1; cmd2; cmd3          # chaining forbidden
```

Aliases cannot:
- contain semicolons  
- be destructive  
- redefine built-in commands  
- include variables (not substituted)  

---

## 12.5 Alias Execution Model

Execution steps:

1. User types alias  
2. CMC resolves alias  
3. Single expanded command executes  
4. Respects flags / confirmations  
5. Cannot expand into multiple commands  

---

Continue next section:  
**13. Quick Path Index Internals & AI Rules**

# 13. QUICK PATH INDEX — INTERNALS & AI RULES  
This section documents how the quick path indexing system works, what `/qbuild`, `/qfind`, and `/qcount` do internally, and how the AI must interact with them.

---

## 13.1 Path Index Architecture

CMC uses the standalone module:

**`path_index_local.py`**  
Located at:
```
C:/Users/Wiggo/Desktop/CentreIndex/paths.db
```

This module performs:
- High‑speed disk scanning  
- Path normalization  
- SQLite‑based storage  
- FTS5 fuzzy-searching (if available)  

The index is stored in **paths.db** and persists between CMC sessions.

---

## 13.2 `/qbuild` — Rebuild the Entire Index

### Purpose  
Scans one or more drives or folders and records *all* file/folder paths.

### Behavior:
- Deletes old index entries  
- Recursively scans targets  
- Stores normalized paths (forward slashes)  
- Can index millions of entries  
- Automatically uses FTS5 if supported  

### AI Rules:
- NEVER suggest `/qbuild` unless:
  - User explicitly says “rebuild index”
  - OR user explicitly asks to index drives
- NEVER auto-run `/qbuild` inside macros
- `/qbuild` requires explicit drive list:
  ```
  /qbuild C,E,F
  /qbuild C:/Users/Wiggo
  ```

---

## 13.3 `/qfind <query>` — Fuzzy Search

### Purpose  
Search the indexed paths using multi-word fuzzy matching.

### Behavior Rules (AI must memorize):

- Split query into terms  
- Perform **AND** match first  
- If not enough results, perform **OR** match  
- Combine results by score  
- Return a max of 50 by default (CMC often uses ~15)

### AI Rules:
- Always lowercase search terms when generating queries.
- Use short, simple search expressions for best results.
- Only use `/qfind` when the user wants to search *globally*.
- Use `find` instead for current-directory search.

---

## 13.4 `/qcount` — Count Indexed Paths

Returns the number of paths stored in `paths.db`.

AI Rules:
- Only generate when user explicitly asks.
- Never use `/qcount` inside automation unless the user is testing.

---

## 13.5 Text Search Helper — `search 'text'`

This command uses:
- `/qfind` to gather candidate files  
- Performs textual search inside those files  
- Only searches text-like files (.txt, .log, .json, .md, .cfg, etc.)

AI Rules:
- Use only when user explicitly wants to search file contents.
- NEVER call `search` with paths, only with **quoted text terms**:
  ```
  search 'database error'
  ```

---

## 13.6 Safety Rules for AI

AI must:
- Avoid huge `/qbuild` operations unless user understands cost.
- Prefer `/qfind` only when local folder search fails or user asks for global search.
- Never generate `/qbuild` in a macro.

---

# 14. PROJECT SYSTEM — INTERNALS & AI RULES

This includes:
- `projectsetup`
- `websetup`
- `webcreate` (via CMC_Web_Create.py)

---

## 14.1 `projectsetup`

Purpose:
- Detects project type (Python, Minecraft server, generic folder)
- Offers to initialize:
  - venv (Python)
  - README
  - Git repo
  - Basic scripts (start_server.bat, etc.)

AI Rules:
- Only generate `projectsetup` if the user states they're inside a project folder.
- Never generate inside system directories.
- For Minecraft servers:
  ```
  cd 'C:/Path/Server';
  projectsetup
  ```
- Always avoid combining with destructive commands.

---

## 14.2 `websetup`

Purpose:
- Detect web project structure (React/Vue/Svelte/Vanilla)
- Generate README, .gitignore, scripts, etc.

AI Rules:
- Only generate when user states they're working on a web project.
- Must be run inside a folder that contains:
  - `package.json`  
  - OR typical framework files  
- Never run it at root of system drives.

---

## 14.3 `webcreate`

Handled by **CMC_Web_Create.py**, which you uploaded.

Capabilities:
- Creates a new root folder
- Creates optional:
  - `client/` (React/Vue/Svelte/Vanilla)
  - `server/` (Express, Flask, FastAPI)
- Automatically runs `npm install` and `pip install`
- Creates `start_app.bat`

AI Rules:
- Only generate with explicit user consent (it writes many files).
- Always ensure user specifies:
  - Project name
  - Target folder
  - Frontend/backend types
- Never mix this with destructive commands.
- Always warn users if destination folder isn’t empty.

---

# 15. JAVA & SERVER LOGIC — INTERNALS & AI RULES

CMC includes a robust system for managing Java runtimes and launching servers.

---

## 15.1 `java list`

Lists installed Java versions that CMC knows about.

AI Rules:
- Never guess Java installation locations.
- Never assume versions other than 8, 17, 21.

---

## 15.2 `java version`

Prints the currently active version.

---

## 15.3 `java change <8|17|21>`

Switches Java_HOME and PATH internally.

AI Rules:
- Only generate one of:
  ```
  java change 8
  java change 17
  java change 21
  ```

---

## 15.4 `java reload`

Re-detect Java installs.

AI Rules:
- Only generate when user indicates new JDKs were installed.

---

## 15.5 Server Launch Logic (Minecraft, ATLauncher, etc.)

Common pattern:
```
cd 'C:/Path/To/Server'
run 'LaunchServer.bat'
```

AI Rules:
- Run servers using `run 'LaunchServer.bat' in '<folder>'`
- Use absolute paths when unclear
- Never generate server deletion commands
- Use Java change commands only if user mentions MC modpacks requiring specific versions

---

# 16. AUTOMATION ENGINE — INTERNALS & AI RULES  
This section details the behavior of `run`, `sendkeys`, `sleep`, and `timer`.

---

## 16.1 `run '<file>' [in '<folder>']`

Supported file types:
- .bat / .cmd
- .exe
- .py (runs via Python)
- .vbs (runs via wscript)

AI Rules:
- ALWAYS include quotes
- ALWAYS include `in` when folder context differs
- NEVER generate `run` commands for:
  - system-critical EXEs
  - PowerShell scripts
  - executables in Windows folders (unless explicitly asked)

---

## 16.2 `sendkeys "<text>"`

AI Rules:
- Double quotes ONLY
- Must escape `{ENTER}` using braces
- Only generate when user explicitly asks for automation

---

## 16.3 `sleep <seconds>`

Pauses script.

AI Rules:
- Use inside macros
- ONLY generate integer seconds

---

## 16.4 `timer <seconds> [msg]`

Countdown timer.

AI Rules:
- Optional message must NOT use quotes unless needed
- No chained messaging inside timer

---

# 17. DOWNLOAD & WEB COMMANDS — INTERNALS & AI RULES

Commands:
- `open <url>`
- `download <url> [target]`
- `download_list <file>`
- `youtube <query>`
- `search web <query>`

AI Rules:
- Never suggest downloads without user intent
- Use absolute paths for download targets
- Never disable SSL unless user explicitly requests

---

Continue next:  
**18. COMPLETE COMMAND LIBRARY (AI-optimized listing)**  
**19. AI Usage Model Summary**  
**20. End of Manual**

# 18. COMPLETE COMMAND LIBRARY (AI-OPTIMIZED SUMMARY)
This section provides a compact reference of ALL commands CMC currently supports.
AI models must memorize this section for accurate command generation.

---

## 18.1 Navigation
```
cd '<path>'
cd ..
cd
ls
dir
list
pwd
whereami
open '<file_or_url>'
explore '<folder>'
```

---

## 18.2 File & Folder Operations
```
create file '<name>' in '<folder>'
create folder '<name>' in '<folder>'
read '<file>'
head '<file>'
tail '<file>'
copy '<src>' '<dst>'
move '<src>' '<dst>'
rename '<src>' '<dst>'
delete '<path>'
zip '<zipfile>' '<target>'
unzip '<zipfile>' ['<folder>']
backup '<src>' '<dst>'
```

---

## 18.3 Search & Path Index
```
find '<pattern>'
findext '<.ext>'
recent
biggest
search '<text>'
/qbuild <drives_or_paths>
/qfind <term>
/qcount
```

---

## 18.4 Macros
```
macro add <name> = <commands>
macro run <name>
macro delete <name>
macro clear
macro list
```

---

## 18.5 Aliases
```
alias add <name> = <single_command>
alias delete <name>
alias list
```

---

## 18.6 Git Helpers
```
/gitsetup
/gitlink '<url>'
/gitupdate "<message>"
/gitpull
/gitstatus
/gitlog
/gitignore add '<pattern>'
/gitclean
/gitdoctor
```

---

## 18.7 Java Tools
```
java list
java version
java change <8|17|21>
java reload
```

---

## 18.8 Automation Engine
```
run '<path>' [in '<folder>']
sleep <seconds>
timer <seconds> [message]
sendkeys "<keys>"
```

---

## 18.9 Web Commands
```
download '<url>' ['<target>']
download_list '<txtfile>'
youtube <query>
search web <query>
open <url>
```

---

## 18.10 Project Tools
```
projectsetup
websetup
webcreate
```

---

## 18.11 Flags
```
batch on | batch off
dry-run on | dry-run off
ssl on | ssl off
```

---

# 19. AI-USAGE SUMMARY (HOW AN AI MUST OPERATE CMC)

This section defines the “mental model” an AI must follow to correctly serve as the embedded CMC assistant.

---

## 19.1 Always Determine Intent First
AI must categorize each user message as:
- Command request  
- Explanation request  
- Mixed  
- Unsafe/destructive  
- Clarification needed  

---

## 19.2 Always Generate Valid CMC Syntax
AI must:
- Use single quotes for paths  
- Use forward slashes  
- Never invent commands  
- Never guess missing information  
- Use semicolons for chaining  
- Avoid trailing semicolons  

---

## 19.3 Always Respect Safety Rules
AI must not suggest destructive commands, batch mode, SSL off, or git-clean unless explicitly requested.

---

## 19.4 Never Invent Future Features
AI must ONLY use commands documented in this manual.

---

## 19.5 Only Output Commands When User Wants Commands
Otherwise explain in normal language.

---

## 19.6 Ask for Clarification When Needed
If path, file, target folder, or destructive intent is unclear → ask ONE clarifying question.

---

## 19.7 Macro Creation Rules
When generating macros:
- Use chained commands with semicolons  
- No destructive commands unless explicitly requested  
- Use absolute paths if context unclear  
- No trailing semicolon  
- Keep names concise and safe  

---

## 19.8 Alias Creation Rules
- Single command only  
- No semicolons  
- No destructive commands  

---

## 19.9 When AI Must Refuse
AI must refuse:
- Dangerous deletion  
- Modifying system folders  
- Running unknown executables  
- Overwriting project structures without permission  
- Unsafe automation  

---

## 19.10 Response Format Rules
- Code blocks ONLY for commands  
- Explanations outside the code blocks  
- Never mix comments inside code blocks  

---

# 20. END OF MANUAL  
This completes the **CMC_AI_Manual.md — AI-Only Edition**.

Any LLM reading this document must now fully understand:
- All valid CMC commands  
- How to generate correct syntax  
- How to follow safety & intent rules  
- How macros, aliases, and flags work  
- How to reason about destructive actions  
- How path indexing and project setup behave  
- How to operate as the embedded CMC assistant  

This manual supersedes all older versions.  
It must be kept alongside CMC so the internal AI assistant can function correctly.

# END OF FILE



## 8. Macros — Advanced, Full-Capability Automation (Unlimited Commands)

Macros in this CMC build are one of the most powerful features available. They allow you to chain **unlimited** commands into a single reusable automation block. Macros execute sequentially, top to bottom, using the exact same parser as normal CMC input.

Macros are saved permanently in the user's macro storage and persist between sessions.

### 8.1 Syntax Overview

```
macro add <name> = <command1>; <command2>; <command3>; ...
```

- `<name>` must be a single word (letters, digits, underscores).
- Macro bodies support **unlimited commands**, separated by `;`.
- Whitespace around `;` is optional.
- Commands execute in order from left to right.

Example:
```
macro add publish = batch on; zip 'C:/Project' to 'C:/Backup'; /gitupdate "Backup %DATE%"; batch off
```

### 8.2 What Macros Can Contain

Macros may include **ANY** CMC command, including but not limited to:

- File operations (`copy`, `move`, `rename`, `delete`)
- Folder creation and file creation
- `zip` / `unzip` / `backup`
- Automation commands (`run`, `sleep`, `timer`, `sendkeys`)
- Java commands (`java change`, `java list`, etc.)
- Web commands (`download`, `search web`)
- Flag commands (`batch on/off`, `dry-run on/off`, `ssl off`)
- Git helpers (`/gitupdate`, `/gitpull`)
- Project tools (`projectsetup`, `websetup`, `webcreate`)

Everything that works in normal CMC works inside macros.

### 8.3 Variable Expansion

Macros support automatic variable expansion:

- `%DATE%` → Current date (YYYY-MM-DD)
- `%NOW%` → Current date and time (YYYY-MM-DD_HH-MM-SS)
- `%HOME%` → User home directory

Example:
```
macro add backup_server = backup '%HOME%/Server' '%HOME%/Backups/Server_%NOW%'
```

### 8.4 Execution Behavior

When running:

```
macro run <name>
```

CMC executes each command in the macro exactly as if you typed it manually. 

Important behaviors:

1. **Flags inside macros take effect immediately**
   Example:
   ```
   batch on; delete 'C:/X'; batch off
   ```

2. **`sendkeys` operates on the active window**
   Useful when paired with `run` commands.

3. **`sleep` pauses macro execution**
   Example:
   ```
   sleep 2
   ```

4. **Paths inside macros follow the same rules as normal commands**
   - Must be single-quoted
   - Use forward slashes
   - Case sensitivity applies in dry-run mode

### 8.5 Common Patterns

#### Macro for publishing a project

```
macro add publish = batch on; zip '%HOME%/Project' to '%HOME%/Desktop'; /gitupdate "Publishing %NOW%"; batch off
```

#### Macro for launching a server

```
macro add start_server = run '%HOME%/Server/start.bat' in '%HOME%/Server'; sleep 3; sendkeys "say Server started!{ENTER}"
```

#### Macro for full automation chain

```
macro add nightly_backup = batch on; backup '%HOME%/Server' '%HOME%/Backups/Server_%NOW%'; sleep 1; /gitupdate "Nightly backup %DATE%"; batch off
```

### 8.6 Inspecting & Managing Macros

List all macros:
```
macro list
```

Delete a macro:
```
macro delete <name>
```

Remove all macros:
```
macro clear
```

### 8.7 Debugging Macros

- Run macros with `dry-run on` to inspect execution.
- Large chains (20+ commands) are supported.
- If one command fails, CMC continues to the next one.
- Use `sleep` to handle race conditions with window focus and `sendkeys`.

### 8.8 Recommendations for AI Usage

When generating macros:

- Always verify command syntax.
- Never wrap the entire macro body in quotes.
- Prefer simple paths (`C:/Users/...`).
- Add comments **outside** macros, not inside them.
- Use variables for portable macros.
