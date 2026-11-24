$ErrorActionPreference = "Stop"

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$startup = [Environment]::GetFolderPath("Startup")
$lnkPath = Join-Path $startup "孙笑川桌宠.lnk"

$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut($lnkPath)
$lnk.TargetPath = Join-Path $env:WINDIR "System32\wscript.exe"
$lnk.Arguments = '//B "' + (Join-Path $dir "启动桌宠.vbs") + '"'
$lnk.WorkingDirectory = $dir
$lnk.WindowStyle = 1
$lnk.Description = "孙笑川闲庭信步桌宠（开机自动启动）"
$lnk.IconLocation = (Join-Path $env:WINDIR "System32\wscript.exe") + ",0"
$lnk.Save()

if (Test-Path -LiteralPath $lnkPath) {
    Write-Host "已设置开机启动："
    Write-Host "  $lnkPath"
} else {
    throw "创建开机启动快捷方式失败"
}
