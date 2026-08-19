# git-push.ps1 — 在 DSH 沙箱环境中推送 zhishu-mingxi 到 GitHub
# 用法: powershell -File scripts/git-push.ps1 [git push 参数...]
# 说明: 沙箱内 git 无法写全局 .gitconfig 且 sh.exe 无法创建 signal pipe，
#       因此用 GIT_CONFIG_GLOBAL 绕过全局配置(去掉 core.sshcommand 的 connect 包装)，
#       并用 GIT_SSH 让 git 直接执行 ssh.exe(不经 sh 包装)，ssh 直连 github.com:22(该端口沙箱放行)。
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot

$env:GIT_CONFIG_GLOBAL = Join-Path $repo ".git\alt-global.gitconfig"
$env:GIT_SSH = "C:\Windows\System32\OpenSSH\ssh.exe"

git -C $repo push @args
exit $LASTEXITCODE
