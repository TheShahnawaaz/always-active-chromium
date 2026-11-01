$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') {
  throw 'This script is restricted to ephemeral GitHub-hosted runners.'
}
Get-Volume | Select-Object DriveLetter, FileSystemType, Size, SizeRemaining | ConvertTo-Json
if (-not (Test-Path D:\)) { throw 'Expected the measured GitHub-hosted D: build volume.' }
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$vs = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vs) { throw 'Visual Studio C++ toolchain not found.' }
& $vswhere -latest -products '*' -format json
"vs2026_install=$vs" >> $env:GITHUB_ENV
'DEPOT_TOOLS_WIN_TOOLCHAIN=0' >> $env:GITHUB_ENV
'AA_BUILD_ROOT=D:\aacc' >> $env:GITHUB_ENV
Set-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled -Value 1
git config --global core.longpaths true
$sdk = "${env:ProgramFiles(x86)}\Windows Kits\10\Include\10.0.28000.0"
if (-not (Test-Path $sdk)) {
  $installer = Join-Path $env:RUNNER_TEMP 'aacc-winsdksetup.exe'
  Invoke-WebRequest -Uri 'https://download.microsoft.com/download/38ab8f6d-3676-4860-ae84-3361308b9d7f/KIT_BUNDLE_WINDOWSSDK_MEDIACREATION/winsdksetup.exe' -OutFile $installer
  $signature = Get-AuthenticodeSignature $installer
  if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Microsoft Corporation') {
    throw 'Windows SDK installer does not have a valid Microsoft signature.'
  }
  $arguments = '/features OptionId.DesktopCPPx64 OptionId.DesktopCPPx86 OptionId.WindowsDesktopDebuggers OptionId.UWPCPP OptionId.SigningTools /q /norestart /ceip off'
  $process = Start-Process -FilePath $installer -ArgumentList $arguments -PassThru -Wait
  if ($process.ExitCode -notin @(0, 3010)) { throw "Windows SDK installation failed: $($process.ExitCode)" }
  Remove-Item $installer
}
if (-not (Test-Path $sdk)) { throw 'Required Windows SDK 10.0.28000.0 missing after installation.' }
Get-Item $sdk | Select-Object FullName
Get-Volume | Select-Object DriveLetter, Size, SizeRemaining | ConvertTo-Json
