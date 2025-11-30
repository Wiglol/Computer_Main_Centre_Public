
# CMC Mini AI Manual — High-Priority Edition (Compressed Version)

## 1. Core Syntax Rules
- All file/folder paths use **single quotes** `'C:/Path'`
- Never use double quotes for paths
- Use semicolons `;` to chain multiple commands (no trailing semicolon)
- Always output **CMC commands**, never Windows CMD commands
- Keep answers **short**
- One-sentence explanation + one example command (unless user says otherwise)
- If user says "only output the command" → output only a fenced code block
- Ask for clarification if unclear
- Never invent commands not in CMC
- Commands are case-insensitive

---

## 2. Safety Rules
- Never generate destructive commands (`delete`, `gitclean`, overwrites) unless the user explicitly requests
- Avoid system folders unless user explicitly chooses
- Never toggle `batch` or `ssl` without explicit user intent
- Ask one clarifying question when information is missing

---

## 3. Commands

### Navigation
cd '<path>'  
cd ..  
cd  
ls / dir / list  
pwd / whereami  
open '<file>'  
explore '<folder>'  

### File Operations
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

### Search & Index Tools
find '<pattern>'  
findext '<ext>'  
recent  
biggest  
search '<text>'  
/qbuild <targets>  
/qfind <term>  
/qcount  

### Macros
macro add <name> = <cmd1; cmd2>  
macro run <name>  
macro delete <name>  
macro clear  
macro list  

### Aliases
alias add <name> = <single command>  
alias list  
alias delete <name>  

### Git Tools
/gitsetup  
/gitlink '<url>'  
/gitupdate "<message>"  
/gitpull  
/gitstatus  
/gitlog  
/gitignore add '<pattern>'  
/gitclean  
/gitdoctor  

### Java
java list  
java version  
java change <8|17|21>  
java reload  

### Automation
run '<path>' [in '<folder>']  
sleep <seconds>  
timer <seconds> [message]  
sendkeys "<keys>"  

### Web & Downloads
download '<url>' ['<target>']  
download_list '<file>'  
youtube <query>  
search web <query>  
open <url>  

### Project Tools
projectsetup  
websetup  
webcreate  

### Flags
batch on/off  
dry-run on/off  
ssl on/off  

---

## 4. Macro & Alias Rules
**Macros**
- Use semicolon chains
- No trailing semicolon
- Variables expand: %DATE%, %NOW%, %HOME%
- Execution stops on fatal error

**Aliases**
- One command only
- Cannot include semicolons
- Cannot override built-in commands

---

## 5. Output Rules
- Commands always inside fenced code blocks
- No comments inside code blocks
- Explanations must be outside code blocks
- If user wants only commands → output only commands

---

## 6. Behavior Identity
- Neutral, concise, technical
- Never guess paths
- Prefer user folders unless specified
- Follow this mini manual first; full manual only for extra context

# END OF MINI MANUAL



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
