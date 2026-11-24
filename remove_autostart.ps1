$startup = [Environment]::GetFolderPath("Startup")
$lnkPath = Join-Path $startup "孙笑川桌宠.lnk"

if (Test-Path -LiteralPath $lnkPath) {
    Remove-Item -LiteralPath $lnkPath -Force
    Write-Host "已取消开机启动。"
} else {
    Write-Host "没有找到开机启动项（可能已经取消）。"
}
