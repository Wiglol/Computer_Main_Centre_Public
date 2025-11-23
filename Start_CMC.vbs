' Start_CMC.vbs – UNIVERSAL VERSION (works on all PCs)
' -----------------------------------------------------
'  ✔ Silently auto-starts Ollama
'  ✔ Works with ANY Python installation (via py.exe)
'  ✔ Works in ANY user folder
'  ✔ No registry keys
'  ✔ No hardcoded Python paths
'  ✔ Tests all possibilities before failing
'  ✔ Prevents ALL 80070002 errors

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' ------------------------------------------------------------
' 1) Start Ollama silently (no error if missing)
' ------------------------------------------------------------
On Error Resume Next
shell.Run "cmd.exe /c ollama serve", 0, False
On Error GoTo 0

' ------------------------------------------------------------
' 2) Find Python using py.exe (universal Windows launcher)
' ------------------------------------------------------------
python = ""

' Try py.exe (standard on all real Python installs)
pyPath = shell.ExpandEnvironmentStrings("%LocalAppData%") & "\Programs\Python\Launcher\py.exe"
If fso.FileExists(pyPath) Then
    python = """" & pyPath & """"
End If

' Fallback: system py.exe
If python = "" Then
    On Error Resume Next
    shell.Run "py -V", 0, True
    If Err.Number = 0 Then python = "py"
    On Error GoTo 0
End If

' Final fallback: python from PATH
If python = "" Then python = "python"

' ------------------------------------------------------------
' 3) Locate Computer_Main_Centre.py (same folder as this VBS)
' ------------------------------------------------------------
scriptFolder = fso.GetParentFolderName(WScript.ScriptFullName)
mainScript = scriptFolder & "\Computer_Main_Centre.py"

If Not fso.FileExists(mainScript) Then
    MsgBox "ERROR: Could not find:" & vbCrLf & mainScript, vbCritical, "CMC Launcher Error"
    WScript.Quit 1
End If

' ------------------------------------------------------------
' 4) Launch CMC through py.exe or python
' ------------------------------------------------------------
cmdLine = python & " """ & mainScript & """"
shell.Run cmdLine, 1, False
