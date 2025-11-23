
# Computer Main Centre (CMC)
### Local Command Console for Windows  

CMC is a **local automation console** for Windows that combines:

- File management  
- Git tools  
- Macros & automation  
- Java version management  
- Quick path indexing  
- Web utilities  
- Download tools  
- Safe execution modes  
- A fully embedded **local AI assistant** powered by **Ollama**

CMC is designed to make your Windows environment **faster, safer, smarter**, and fully offline-capable.

---

## 🚀 Features

### 🟦 Core Console Capabilities
- Full file operations: create/read/move/delete/zip/unzip  
- Safe modes: Dry-Run, Batch, SSL toggle  
- Persistent macros & aliases  
- Fast file search with `/qbuild`, `/qfind`  
- Autocompletion  
- Git helper commands  
- Java switching (`java list`, `java change`)  
- Download helpers (`download`, `download_list`, `youtube`, `search web`)  
- Project setup tools (`projectsetup`, `websetup`, `webcreate`)

---

## 🤖 AI Features (Offline)

CMC includes an embedded AI assistant using **Ollama**:

```
ai <your question>
```

The assistant:

- Runs **fully offline**  
- Generates **valid CMC commands**  
- Uses single-quoted paths  
- Creates macros  
- Explains commands  
- Respects safety rules  
- Reads `CMC_AI_Manual_MINI.md` 

---

## 🧩 File Overview

```
CMC/
│ Computer_Main_Centre.py      ← Main console application
│ assistant_core.py            ← Embedded AI engine
│ CMC_AI_Manual_MINI.md        ← Mini manual the AI uses
│ CMC_AI_Manual.md             ← Full reference manual (optional)
│ CMC_AI_Ollama_Setup.cmd      ← Auto-installs AI model
│ Start_CMC.vbs                ← Universal launcher
│ README.md                    ← This file
└ (misc files...)
```

---

## 🧰 Requirements

- Windows 10 or 11  
- Python 3.10+  
- Ollama (for AI mode): https://ollama.com/download  
- No internet required after installation

---

## 🛠 Installation Guide

### 1. Install Python  
From https://python.org/downloads — check “Add to PATH”.

### 2. Install Ollama  
Download from https://ollama.com/download  
Run it once so the service initializes.

### 3. Get CMC  
Download or clone the repository.

### 4. Run AI Setup Script  
Inside the CMC folder:

```
CMC_AI_Ollama_Setup.cmd
```

This script will:

- Detect Ollama  
- Download `qwen2.5:7b-instruct`  
- Set model environment variable  
- Prepare AI mode automatically  

### 5. Launch CMC  
Double-click:

```
Start_CMC.vbs
```

This will auto-start Ollama silently and launch CMC.

---

## 🤖 Using the AI Assistant

Examples:

```
ai test
ai how do I zip this folder?
ai "create a macro that backs up the project"
ai "only output the command to make a new folder on Desktop"
```

The assistant:

- Outputs short answers  
- Generates valid CMC commands  
- Behaves safely  

---

## 📚 Manuals

### CMC_AI_Manual_MINI.md  
Compressed, AI-optimized manual used by the assistant.

### CMC_AI_Manual.md  
Large full documentation for advanced users or Better AI like chatGPT 5.1 or Grok AI.

---

## ✔ Troubleshooting

- Ensure Ollama is running  
- Ensure Python is installed  
- Re-run setup:  
  ```
  CMC_AI_Ollama_Setup.cmd
  ```

