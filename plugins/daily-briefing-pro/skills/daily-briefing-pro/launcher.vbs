Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

' Get the script directory
scriptDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
runAllPath = scriptDir & "\scripts\run_all.py"

' Run run_all.py and capture output to a log file
logFile = scriptDir & "\data\run_all_log.txt"

' Create data dir if not exists
dataDir = scriptDir & "\data"
If Not objFSO.FolderExists(dataDir) Then
    objFSO.CreateFolder(dataDir)
End If

' Execute Python script, redirect output to log
cmd = "cmd /c python """ & runAllPath & """ > """ & logFile & """ 2>&1"

' Run and wait for completion (timeout 10 minutes = 600 seconds)
objShell.Run cmd, 0, True

WScript.Echo "Done. Log: " & logFile
