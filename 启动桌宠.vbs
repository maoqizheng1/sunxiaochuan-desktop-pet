Option Explicit
' Launch the desktop pet silently (no console window).
'
' pythonw.exe lookup order:
'   1. python_path.txt next to this script (full path to pythonw.exe)
'   2. pythonw.exe in the same folder (portable Python)
'   3. pythonw.exe from PATH
Dim fso, sh, here, pyw, script, cfg, ts

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")

here = fso.GetParentFolderName(WScript.ScriptFullName)
script = here & "\desktop_pet.py"
If Not fso.FileExists(script) Then
    MsgBox "desktop_pet.py not found in " & here, 16, "Desktop Pet"
    WScript.Quit 1
End If

pyw = ""
cfg = here & "\python_path.txt"
If fso.FileExists(cfg) Then
    Set ts = fso.OpenTextFile(cfg, 1)
    pyw = ts.ReadAll
    ts.Close
    pyw = Replace(pyw, vbCr, "")
    pyw = Replace(pyw, vbLf, "")
    pyw = Trim(pyw)
End If

If pyw = "" Or Not fso.FileExists(pyw) Then
    If fso.FileExists(here & "\pythonw.exe") Then
        pyw = here & "\pythonw.exe"
    Else
        pyw = "pythonw.exe"
    End If
End If

sh.CurrentDirectory = here
sh.Run """" & pyw & """ """ & script & """", 0, False
