CMC_AI_MINI_SPEC (Expanded)
GROUND TRUTH. Use ONLY these commands + their documented variants.
Paths MUST use single quotes. Chain commands with ';' (no trailing ';').

CORE RULES:
- Paths: ALWAYS single quotes: cd 'C:/Users/Name/Desktop'
- Chain: cmd1; cmd2; cmd3
- If user asks "what do I type" → output commands inside a ```cmc``` block
- Destructive commands only if user explicitly asked (delete, git repo delete, /gitclean, etc.)
- Prefer: dry-run on before risky ops
- batch on auto-confirms prompts (danger)
- ssl on/off affects downloads

STATUS / SAFETY:
status            (shows Batch / SSL / Dry-Run, and may show AI model if enabled)
log               (recent ops)
undo              (only move/rename undo)
shell             (opens system shell; may require confirm unless batch on)

NAV:
cd '<path>' | cd .. | cd (HOME) | home | back
pwd / whereami
ls / dir / list

OPEN:
open '<file-or-url>'
explore '<folder>'

FILES:
read/head/tail '<file>'
create folder '<name>' in '<path>'
create file '<name>' in '<path>'
write '<file>' <text>          (may confirm overwrite; respects dry-run)
copy '<src>' to '<dst>'
move '<src>' to '<dst>'
rename '<src>' to '<dst>'
delete '<path>'                (danger; confirm unless batch on; respects dry-run)

ZIP / BACKUP:
zip '<source>' to '<destination-folder>'
unzip '<zipfile.zip>' to '<destination-folder>'
backup '<source>' '<destination-folder>'   (timestamped zip)

SEARCH:
find '<pattern>'
findext '.ext'
recent
biggest
search '<text>'                (search inside files)

PATH INDEX (fast global):
/qbuild C D E
/qfind <query>
/qcount

SPACE (disk usage, safe):
space
space '<path>'
space '<path>' depth <n>
space '<path>' depth <n> report
space '<path>' full

MACROS:
macro add <name> = <cmd1>; <cmd2>; ...
macro run <name>
macro list
macro delete <name>
macro clear
Vars: %HOME%  %DATE%  %NOW%

ALIASES (one command only, no ';'):
alias add <name> = <cmd>
alias list
alias delete <name>

GIT (friendly, fastest publishing):
git upload
  - Creates a new GitHub repo from current folder
  - Initializes git if needed, commits, pushes, stores folder→repo mapping
  - Creates/updates .gitignore (untracked-only; does not remove already-tracked files)

git update
  - Commits + pushes to the linked repo for this folder (mapping/origin)
  - If nothing changed → still tries to push (may show “Nothing to commit.”)

git update "<message>"
  - Uses the quoted text as commit message (does NOT change repo link)

git update <owner>/<repo> ["message"]
  - Sets origin to that repo (and/or updates mapping), then commits + pushes

git update <owner>/<repo> ["message"] --add <file_or_folder>
  - Partial commit: only adds/commits that path, then pushes

git download <owner>/<repo>
  - Clones the repo into current folder (some builds also accept: git clone)

git link <owner>/<repo>   (or GitHub URL)
  - Sets origin for current folder (needed for org/classroom repos)
  - Example: git link MyOrg/AssignmentRepo

git status
git log
git doctor
git repo list
git repo delete <repo>   (danger; deletes on GitHub; local untouched)

GIT (self-healing, when git is cursed):
git force upload
git force update [<owner>/<repo>] ["message"] [--add <path>]
git debug upload
git debug update [<owner>/<repo>] ["message"] [--add <path>]

Force/Debug behavior:
- Tries to auto-fix common problems:
  - missing init, wrong/missing main branch
  - missing first commit (refspec main does not match any)
  - index.lock stuck
  - origin mismatch (when a valid owner/repo is provided)
- If it still fails, it prints + saves a big debug report file (CMC_GIT_DEBUG_*.txt)
- If origin contains '<you>' placeholder, force should stop and tell you to fix origin

JAVA / PROJECT:
java list
java version
java change 8|17|21
java reload
projectsetup
websetup
webcreate

RUN / AUTO:
run '<path>'
run '<script>' in '<folder>'
sleep <sec>
timer <sec> [message]
sendkeys "text{ENTER}"   (only if user asked)

DOWNLOAD / WEB:
search web <query>
youtube <query>
download '<url>' ['<file>']
downloadlist '<txtfile>'   (some builds: download_list)

AI + OBSERVER:
ai <question>
ai-model list
ai-model current
ai-model set <model>
Aliases:
model list | model current | model set <model>

