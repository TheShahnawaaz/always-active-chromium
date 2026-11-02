# Read-only failure evidence for one already-verified test-owned browser root.
# Invoked only after a failed passive observation; no UI actions or global UI walk.
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$clock=[Diagnostics.Stopwatch]::StartNew()
$limitNodes=64; $limitDepth=6; $limitChildren=32
$roleNames=@('renderer','gpu-process','utility','crashpad-handler','other')
$utilityNames=@('network','audio','storage','video-capture','other')
function Verify-Owned {
  $p=Get-CimInstance Win32_Process -Filter ('ProcessId='+$env:AA_NO_DEBUG_PID) -OperationTimeoutSec 2
  if($null -eq $p -or $p.CreationDate.ToUniversalTime().ToString('o') -cne $env:AA_NO_DEBUG_STARTED -or -not [string]::Equals($p.ExecutablePath,$env:AA_NO_DEBUG_EXECUTABLE,[StringComparison]::OrdinalIgnoreCase) -or $p.CommandLine -cne $env:AA_NO_DEBUG_COMMAND){throw 'owned_identity_changed'}
  return $p
}
function Emit-Receipt { $script:receipt | ConvertTo-Json -Depth 7 -Compress }
function Add-Tags([string]$text) {
  if($null -eq $text -or $text.Length -gt 2048){return}
  foreach($match in [regex]::Matches($text,'\b(?:ERR|STATUS|RESULT_CODE)_[A-Z0-9_]{1,64}\b')) {
    if($script:tags.Count -lt 16){[void]$script:tags.Add($match.Value)}
  }
  if($text -match '(?i)\bAw[,]?\s+Snap\b' -and $script:tags.Count -lt 16){[void]$script:tags.Add('Aw Snap')}
  if($text -match '(?i)\bPage unresponsive\b' -and $script:tags.Count -lt 16){[void]$script:tags.Add('Page unresponsive')}
  if($text -match '(?i)\b(?:Choose your search engine|Set up your browser|Sign in to Chrome|Make Chrome your default browser)\b' -and $script:tags.Count -lt 16){[void]$script:tags.Add('startup-choice')}
}
function Classify-Address([string]$value) {
  if($null -eq $value -or $value.Length -gt 2048){return 'unavailable'}
  $value=$value.Trim()
  if($value.Length -eq 0 -or $value -ceq 'about:blank'){return 'blank'}
  foreach($expected in $script:expectedUrls) {
    if($value -ceq $expected -or $value -ceq ($expected -replace '^http://','')){return 'expected-loopback'}
  }
  if($value -match '^(?:chrome(?:-untrusted|-search|-extension)?|about|devtools):'){return 'internal'}
  return 'other'
}
try {
  if($env:AA_NO_DEBUG_PID -notmatch '^[1-9][0-9]{0,8}$' -or [int]$env:AA_NO_DEBUG_PID -le 4){throw 'invalid_owned_pid'}
  $root=Verify-Owned
  $expectedUrls=ConvertFrom-Json $env:AA_NO_DEBUG_URLS
  if($expectedUrls -isnot [Array] -or $expectedUrls.Count -ne 2){throw 'invalid_expected_urls'}
  foreach($url in $expectedUrls) {
    if($url -isnot [string] -or $url.Length -gt 256 -or $url -notmatch '^http://127\.0\.0\.1:[0-9]{1,5}/page/(?:alpha|beta)\?run=[0-9a-f-]{36}$'){throw 'invalid_expected_urls'}
  }
  $roles=[ordered]@{};foreach($name in $roleNames){$roles[$name]=0}
  $utilities=[ordered]@{};foreach($name in $utilityNames){$utilities[$name]=0}
  $children=[ordered]@{status='unavailable';examined=0;verified=0;unverified=0;truncated=$false;roles=$roles;utilities=$utilities;creationAndPackageVerified=$true}
  $knownPids=[Collections.Generic.HashSet[int]]::new();[void]$knownPids.Add([int]$root.ProcessId)
  $package=[IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($root.ExecutablePath)).TrimEnd('\')+'\'
  try {
    $snapshot=@(Get-CimInstance Win32_Process -Filter ('ParentProcessId='+$root.ProcessId) -OperationTimeoutSec 2 | Select-Object -First 33)
    $children.truncated=$snapshot.Count -gt $limitChildren
    foreach($child in ($snapshot | Select-Object -First $limitChildren)) {
      $children.examined++
      $valid=$false
      try {
        $exe=[IO.Path]::GetFullPath([string]$child.ExecutablePath)
        $created=$child.CreationDate.ToUniversalTime()
        $valid=$child.ParentProcessId -eq $root.ProcessId -and $child.SessionId -eq $root.SessionId -and $created -ge $root.CreationDate.ToUniversalTime() -and $created -le [DateTime]::UtcNow -and $exe.StartsWith($package,[StringComparison]::OrdinalIgnoreCase) -and [IO.Path]::GetFileName($exe) -in @('chrome.exe','chrome_crashpad_handler.exe') -and $child.CommandLine -is [string] -and $child.CommandLine.Length -le 32768
      } catch {}
      if(-not $valid){$children.unverified++;continue}
      $children.verified++;[void]$knownPids.Add([int]$child.ProcessId)
      # Extract only bounded whole --type / known utility tokens; never retain argv.
      $matches=[regex]::Matches($child.CommandLine,'(?:^|\s)(?:"--type=(?<v>[A-Za-z0-9_-]{1,64})"|--type=(?:"(?<v>[A-Za-z0-9_-]{1,64})"|(?<v>[A-Za-z0-9_-]{1,64})))(?=\s|$)')
      $role='other'
      if($matches.Count -eq 1 -and $matches[0].Groups['v'].Value -in $roleNames){$role=$matches[0].Groups['v'].Value}
      $roles[$role]++
      if($role -eq 'utility') {
        $matches=[regex]::Matches($child.CommandLine,'(?:^|\s)(?:"--utility-sub-type=(?<v>[A-Za-z0-9_.-]{1,96})"|--utility-sub-type=(?:"(?<v>[A-Za-z0-9_.-]{1,96})"|(?<v>[A-Za-z0-9_.-]{1,96})))(?=\s|$)')
        $utility='other'
        if($matches.Count -eq 1) {
          switch -CaseSensitive ($matches[0].Groups['v'].Value) {
            'network.mojom.NetworkService' {$utility='network'}
            'audio.mojom.AudioService' {$utility='audio'}
            'storage.mojom.StorageService' {$utility='storage'}
            'video_capture.mojom.VideoCaptureService' {$utility='video-capture'}
          }
        }
        $utilities[$utility]++
      }
    }
    $children.status='observed'
  } catch { $children.status='unavailable' }
  $null=Verify-Owned
  $process=Get-Process -Id ([int]$root.ProcessId) -ErrorAction Stop
  $handle=$process.MainWindowHandle
  $titleCategory='other'
  if($process.MainWindowTitle -match '^Untitled(?: - |$)'){$titleCategory='untitled'}
  if($process.MainWindowTitle -match '^Native visibility observation(?: - |$)'){$titleCategory='fixture'}
  $tags=[Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
  Add-Tags ([string]$process.MainWindowTitle)
  $receipt=[ordered]@{schema=1;purpose='owned-failed-normal-window-diagnostic';status='partial';pid=[int]$root.ProcessId;started=$env:AA_NO_DEBUG_STARTED;identityReverified=$true;mainWindowHandle=$handle.ToInt64().ToString('x');mainWindowTitleCategory=$titleCategory;mainWindowState=[ordered]@{ownershipVerified=$false;visible=$null;minimized=$null;foreground=$null};childRoles=$children;uia=[ordered]@{status='unavailable';reason='not_completed';ownershipVerified=$false;visitedNodes=0;truncated=$false;addressBar=[ordered]@{status='not-found';category=$null;candidates=0};errorTags=@($tags | Sort-Object)};limits=[ordered]@{maxChildren=32;maxNodes=64;maxDepth=6;maxTags=16;maxTextLength=2048};elapsedMs=[int]$clock.ElapsedMilliseconds}
  # An early sanitized snapshot survives a provider hang killed by the caller.
  Emit-Receipt
  if($handle -eq [IntPtr]::Zero){$receipt.uia.reason='no_owned_window';Emit-Receipt;exit 0}
  try {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class FailedWindowNative {
  [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr hwnd);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hwnd);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hwnd);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
}
'@
    [uint32]$owner=0
    $null=[FailedWindowNative]::GetWindowThreadProcessId($handle,[ref]$owner)
    if(-not [FailedWindowNative]::IsWindow($handle) -or $owner -ne [uint32]$root.ProcessId){throw 'owned_hwnd_unverified'}
    $receipt.mainWindowState=[ordered]@{ownershipVerified=$true;visible=[FailedWindowNative]::IsWindowVisible($handle);minimized=[FailedWindowNative]::IsIconic($handle);foreground=([FailedWindowNative]::GetForegroundWindow() -eq $handle)}
    $null=Verify-Owned
    $receipt.elapsedMs=[int]$clock.ElapsedMilliseconds
    Emit-Receipt
  } catch { $receipt.mainWindowState=[ordered]@{ownershipVerified=$false;visible=$null;minimized=$null;foreground=$null} }
  try {
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes
    $window=[System.Windows.Automation.AutomationElement]::FromHandle($handle)
    $current=$window.Current
    if($current.ProcessId -ne [int]$root.ProcessId -or $current.NativeWindowHandle -ne $handle.ToInt32() -or $current.ControlType -ne [System.Windows.Automation.ControlType]::Window){throw 'owned_window_unverified'}
    $receipt.uia.ownershipVerified=$true
    $walker=[System.Windows.Automation.TreeWalker]::ControlViewWalker
    $queue=[Collections.Generic.Queue[object]]::new();$queue.Enqueue(@($window,0))
    $categories=[Collections.Generic.List[string]]::new()
    $uiClock=[Diagnostics.Stopwatch]::StartNew()
    while($queue.Count -gt 0 -and $receipt.uia.visitedNodes -lt $limitNodes -and $uiClock.ElapsedMilliseconds -lt 3000) {
      $item=$queue.Dequeue();$element=$item[0];$depth=[int]$item[1]
      $receipt.uia.visitedNodes++
      try {
        $data=$element.Current
        if(-not $knownPids.Contains([int]$data.ProcessId)){continue}
        $name=[string]$data.Name
        Add-Tags $name
        # Only the browser's known omnibox label/ID can expose an address value.
        if($data.ControlType -eq [System.Windows.Automation.ControlType]::Edit -and ($name -in @('Address and search bar','Search or enter address') -or $data.AutomationId -ceq 'address and search bar')) {
          $pattern=$null
          if($element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern,[ref]$pattern)) {$categories.Add((Classify-Address ([string]$pattern.Current.Value)))}
          else {$categories.Add('unavailable')}
        }
        if($depth -ge $limitDepth){$receipt.uia.truncated=$true;continue}
        $next=$walker.GetFirstChild($element);$siblings=0
        while($null -ne $next -and $siblings -lt 16 -and $queue.Count -lt $limitNodes -and $uiClock.ElapsedMilliseconds -lt 3000) {
          $queue.Enqueue(@($next,$depth+1));$siblings++;$next=$walker.GetNextSibling($next)
        }
        if($null -ne $next){$receipt.uia.truncated=$true}
      } catch { $receipt.uia.truncated=$true }
    }
    if($queue.Count -gt 0){$receipt.uia.truncated=$true}
    $receipt.uia.addressBar.candidates=$categories.Count
    if($categories.Count -eq 1){$receipt.uia.addressBar.status='classified';$receipt.uia.addressBar.category=$categories[0]}
    elseif($categories.Count -gt 1){$receipt.uia.addressBar.status='ambiguous'}
    $receipt.uia.errorTags=@($tags | Sort-Object)
    $null=Verify-Owned
    $receipt.status='observed';$receipt.uia.status='observed';$receipt.uia.reason=$null
  } catch {
    $receipt.uia=[ordered]@{status='unavailable';reason='bounded_owned_uia_unavailable';ownershipVerified=$false;visitedNodes=0;truncated=$true;addressBar=[ordered]@{status='not-found';category=$null;candidates=0};errorTags=@()}
  }
  $receipt.elapsedMs=[int]$clock.ElapsedMilliseconds
  Emit-Receipt
} catch {
  [pscustomobject]@{schema=1;purpose='owned-failed-normal-window-diagnostic';status='unavailable';reason='bounded_owned_window_probe_failed'} | ConvertTo-Json -Compress
}
