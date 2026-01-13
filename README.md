# Computer Main Centre (CMC)
### Local Command Console for Windows  

CMC is a **local automation console** for Windows that combines powerful tools into a single, consistent command environment:

- File management  
- GitHub publishing  
- Macros & automation  
- Java version management  
- Quick path indexing & search  
- Web project setup tools  
- Download helpers  
- Safe execution modes  
- A fully embedded **local AI assistant** powered by **Ollama**

CMC is designed to make your Windows workflow **faster, safer, and smarter**, while remaining **fully offline-capable**.

---

## 🚀 Features

### 🟦 Core Console Capabilities
- Full file operations: create, read, move, delete, zip, unzip  
- Safe execution modes: **Dry-Run**, **Batch**, **SSL toggle**  
- Persistent macros & aliases  
- Fast global file search with `/qbuild`, `/qfind`, `/find`  
- Command autocompletion  
- Simplified GitHub publishing (`git upload`, `git update`)  
- Java version switching (`java list`, `java change`, `java reload`)  
- Download helpers (`download`, `download_list`, `youtube`, `search web`)  
- Project setup tools (`projectsetup`, `websetup`, `webcreate`)  
- Script & program execution with correct working directories  

---

## 🤖 AI Features (Offline)

CMC includes a built-in AI assistant using **Ollama**:

ai <your question>

markdown
Copy code

The assistant:

- Runs **fully offline**
- Generates **valid CMC commands**
- Uses correct single-quoted paths
- Creates macros & automation
- Explains commands and workflows
- Respects safety modes (Dry-Run, Batch)
- Reads `CMC_AI_Manual-MEDIUM.md` as its knowledge base

The AI is designed to **assist**, not take control.

---

## 🧰 Requirements

- Windows 10 or Windows 11  
- Python 3.10+  
- Git for Windows (for GitHub features)  
- Ollama (for AI mode): https://ollama.com/download  

> Internet access is only required for installation.  
> **CMC and AI mode work fully offline after setup.**

---

## 🛠 Installation

### 1️⃣ Install Python  
Download from https://python.org/downloads  
✔ Check **“Add Python to PATH”** during installation.

### 2️⃣ Install Ollama  
Download from https://ollama.com/download  
Run it once to initialize the service.

### 3️⃣ Get CMC  
Download or clone this repository anywhere on your system.

### 4️⃣ Set up the AI model  
Inside the CMC folder, run:

CMC_AI_Ollama_Setup.cmd

markdown
Copy code

This script will:

- Detect Ollama
- Download `qwen2.5:7b-instruct`
- Configure the model automatically
- Prepare AI mode for use

### 5️⃣ Launch CMC  
Double-click:

Start_CMC.vbs

yaml
Copy code

This will:
- Start Ollama silently (if needed)
- Launch the CMC console

---

## 🤖 Using the AI Assistant

Examples:

ai test
ai how do I zip this folder?
ai create a macro that backs up this project
ai only output the command to create a new folder on Desktop

yaml
Copy code

The assistant:
- Gives short, useful answers
- Outputs valid CMC commands
- Avoids unsafe operations
- Respects your current working directory

---

## 📚 Manuals

### CMC_AI_Manual_MINI.md
Compact, AI-optimized manual used by the embedded assistant.

### CMC_AI_Manual_MEDIUM.md
Full documentation for advanced users or external AI tools.

---

## ✔ Notes & Limitations

- Empty folders are not tracked by Git (Git limitation)
- `.gitignore` rules are always respected
- GitHub repository deletion affects GitHub only (local files stay intact)
- CMC is designed for **local use**, not remote execution

---

## 🛠 Troubleshooting

- Ensure Python is installed and on PATH  
- Ensure Ollama is running  
- Re-run setup if needed:

CMC_AI_Ollama_Setup.cmd

yaml
Copy code

---

## 📌 Philosophy

CMC is built around:
- **Safety first**
- **Explicit commands**
- **No hidden automation**
- **Offline-friendly tooling**

If a command runs, it’s because *you* told it to.

---