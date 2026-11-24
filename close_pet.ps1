$ErrorActionPreference = "SilentlyContinue"

$targets = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
    Where-Object { $_.CommandLine -like "*desktop_pet.py*" }

if ($targets) {
    foreach ($t in $targets) {
        Stop-Process -Id $t.ProcessId -Force
    }
    Write-Host "Desktop pet closed."
} else {
    Write-Host "Desktop pet is not running."
}

Remove-Item -LiteralPath (Join-Path $PSScriptRoot "pet.pid") -Force
Start-Sleep -Milliseconds 300
