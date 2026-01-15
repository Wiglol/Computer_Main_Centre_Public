CMC_AI_MINI_SPEC 
GROUND TRUTH. Use ONLY these commands. Paths MUST use single quotes.
Chain commands with ';' (no trailing ';'). Avoid destructive ops unless user explicitly asks.
Prefer: dry-run on before risky ops. batch on auto-confirms prompts (danger). ssl on/off affects downloads.

NAV:
cd '<path>' | cd .. | cd (HOME) | home | back
pwd/whereami | ls/dir/list | status

OPEN:
open '<file-or-url>' | explore '<folder>'

FILES:
read/head/tail '<file>'
create folder '<name>' in '<path>' | create file '<name>' in '<path>'
write '<file>' <text>
copy '<src>' to '<dst>' | move '<src>' to '<dst>' | rename '<src>' to '<dst>'
delete '<path>'

ZIP/BACKUP:
zip '<source>' to '<destination-folder>'   (makes zip in dest folder)
unzip '<zipfile.zip>' to '<destination-folder>'
backup '<source>' '<destination-folder>'   (timestamped zip)

SEARCH:
find '<pattern>' | findext '.ext' | recent | biggest | search '<text>'

PATH INDEX (fast global):
/qbuild C D E
/qfind <query>      (some builds also allow /find)
/qcount

SPACE (disk usage, safe):
space | space '<path>' | space '<path>' depth <n> | space '<path>' depth <n> report | space '<path>' full

MACROS:
macro add <name> = <cmd1>; <cmd2>; ...
macro run <name> | macro list | macro delete <name> | macro clear
Vars: %HOME% %DATE% %NOW%

ALIASES (one command only):
alias add <name> = <cmd> | alias list | alias delete <name>

GIT (friendly):
git upload | git update | git update <repo> | git clone <owner>/<repo> | git link <owner>/<repo>
git status | git log | git doctor | git repo list | git repo delete <repo> (irreversible on GitHub)

JAVA/PROJECT:
java list | java version | java change 8|17|21 | java reload
projectsetup | websetup | webcreate

RUN/AUTO:
run '<path>' | run '<script>' in '<folder>'
sleep <sec> | timer <sec> [message]
sendkeys "text{ENTER}" (only if user asks)

DOWNLOAD/WEB:
search web <query> | youtube <query>
download '<url>' ['<file>']
downloadlist '<txtfile>'  (some builds: download_list)

LOG/UNDO/SHELL:
log | undo (only move/rename) | shell

AI+OBSERVER:
ai <question>
observer start|stop|status (read-only FS API on localhost)
AI may output ONE line starting with:
OBSERVER: ls path='...' depth=2
OBSERVER: stat path='...'
OBSERVER: tree path='...' depth=2
OBSERVER: find name='pattern' root='...' max=15
Then use returned JSON to answer; no 2nd OBSERVER.
