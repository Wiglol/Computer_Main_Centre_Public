📘 COMPUTER MAIN CENTRE (CMC)
=============================

A local command console for safe file automation, Git integration, and instant path search.

──────────────────────────────
🚀 QUICK START
──────────────────────────────

1. Install **Python 3**  
   → https://www.python.org/downloads/  
   ✔ Check “Add Python to PATH” during setup

2. Open Command Prompt and install dependencies:
   pip install rich requests pyautogui prompt_toolkit

3. (Optional) Install **Git for Windows**  
   → https://git-scm.com/download/win

4. Launch:
   • Double-click **Start_CMC.vbs**
   • Or run:  python Computer_Main_Centre.py


──────────────────────────────
💡 USAGE
──────────────────────────────

• Type `help` inside CMC to see all commands.  
• Use `/qbuild` once to build a fast local index for `/qfind` and `/qcount`.  
• Common examples:
  - `backup 'C:/Users/user/Documents' 'D:/Backups'`
  - `macro add publish = delete 'C:/Public/CMC.py'; copy 'C:/Main/CMC.py' to 'C:/Public'`
  - `batch on; copy 'C:/file.txt' to 'D:/'; batch off`

──────────────────────────────
🔧 TROUBLESHOOTING
──────────────────────────────

If you see:
❌ Error: cannot DELETE from contentless fts5 table: paths_fts  
→ Delete `paths.db` from the CMC folder and rerun `/qbuild`.

──────────────────────────────
☕ GIT FEATURES
──────────────────────────────

CMC can push or pull GitHub repositories directly:
  /gitsetup "RepoName"
  /gitupdate "message"
  /gitpull
  /gitstatus
  /gitdoctor

──────────────────────────────
✅ DONE
──────────────────────────────

You’re ready!  
Start with **Start_CMC.vbs**, type `help`, and explore your automation console.
