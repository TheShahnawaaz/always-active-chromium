# Capture one verified owned normal window. No input, permission or desktop APIs.
param([string]$PidValue, [string]$Profile, [string]$Executable,
      [string]$ExpectedStarted, [string]$OutputFile, [string]$CaptureContext='fixture')
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$script:Clock = [Diagnostics.Stopwatch]::StartNew()
$script:OwnedPid = 0
$script:Report = [ordered]@{ schema=1; purpose='owned-normal-browser-window-capture'; platform='win32'; status='refused'
    captureContext=$CaptureContext; behaviorVerified=$false
    captureAttempted=$false; captureSucceeded=$false; captureOutcomeUncertain=$false; nativeUiAccessed=$false; visitedWindows=0
    manualReview='pending'; uiEquivalenceVerified=$false; visualCompletenessVerified=$false
    identity=@{verified=$false}; window=@{}; png=@{}; errors=@()
    limits=@{maxWidth=2048;maxHeight=1536;maxPixels=3145728;maxPngBytes=3145728;maxWindows=8;internalMs=10000;externalMs=15000} }
function Assert-Budget { if ($script:Clock.ElapsedMilliseconds -ge 10000) { throw 'capture_budget_exceeded' } }
function Title-Kind([string]$Title) {
    if ($null -eq $Title -or $Title.Length -gt 512) { return $null }
    if ($Title.StartsWith('Native visibility observation',[StringComparison]::Ordinal)) { return 'fixture' }
    if ($CaptureContext -ceq 'startup-diagnostic' -and (@('Untitled - Google Chrome for Testing','Untitled - Chromium','Untitled - Google Chrome') -ccontains $Title)) { return 'untitled' }
    return $null
}
function Assert-WindowTitle($Chosen) {
    $current=$Chosen.element.Current
    if ($current.ProcessId -ne $script:OwnedPid -or [long]$current.NativeWindowHandle -ne $Chosen.handle -or $current.IsOffscreen -or $current.Name -cne $Chosen.title -or (Title-Kind $current.Name) -cne $Chosen.titleKind) { throw 'owned_window_title_changed' }
}
function Canonical([string]$Value, [bool]$Directory) {
    if ([string]::IsNullOrEmpty($Value) -or $Value.Length -gt 4096 -or -not [IO.Path]::IsPathRooted($Value) -or [IO.Path]::GetPathRoot($Value).Length -lt 3) { throw 'absolute_path_required' }
    $item = Get-Item -LiteralPath $Value -Force
    if ([bool]$item.PSIsContainer -ne $Directory -or $item.PSProvider.Name -ne 'FileSystem' -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'regular_owned_path_required' }
    return [IO.Path]::GetFullPath($item.FullName).TrimEnd([IO.Path]::DirectorySeparatorChar)
}
function Identity {
    Assert-Budget
    $process = Get-CimInstance Win32_Process -Filter ('ProcessId='+$script:OwnedPid) -OperationTimeoutSec 2
    if ($null -eq $process -or $process.SessionId -ne [Diagnostics.Process]::GetCurrentProcess().SessionId) { throw 'owned_process_or_session_mismatch' }
    $owner = Invoke-CimMethod -InputObject $process -MethodName GetOwnerSid -OperationTimeoutSec 2
    if ($owner.ReturnValue -ne 0 -or $owner.Sid -ne [Security.Principal.WindowsIdentity]::GetCurrent().User.Value) { throw 'owned_process_user_mismatch' }
    $created = $process.CreationDate.ToUniversalTime().ToString('o')
    if ($created -cne $ExpectedStarted -or -not [string]::Equals((Canonical $process.ExecutablePath $false),$script:ExpectedExecutable,[StringComparison]::OrdinalIgnoreCase)) { throw 'owned_creation_or_executable_mismatch' }
    if ([string]::IsNullOrEmpty($process.CommandLine) -or $process.CommandLine.Length -gt 131072) { throw 'owned_arguments_unavailable' }
    $arguments = [OwnedWindowCapture.Native]::Parse($process.CommandLine)
    $profiles = New-Object 'System.Collections.Generic.List[string]'
    for ($index=0;$index -lt $arguments.Length;$index++) {
        $arg=$arguments[$index]
        if ($arg.StartsWith('--user-data-dir=',[StringComparison]::Ordinal)) { $profiles.Add($arg.Substring(16)) }
        elseif ($arg -ceq '--user-data-dir' -and $index+1 -lt $arguments.Length) { $profiles.Add($arguments[$index+1]) }
        if ($arg -match '^--(remote-debugging|enable-automation|headless|load-extension|disable-extensions-except|enable-unsafe-extension-debugging)') { throw 'normal_launch_flags_required' }
    }
    if ($profiles.Count -ne 1 -or -not [string]::Equals((Canonical $profiles[0] $true),$script:ExpectedProfile,[StringComparison]::OrdinalIgnoreCase)) { throw 'owned_profile_mismatch' }
    return @{pid=$script:OwnedPid;executable=$script:ExpectedExecutable;profile=$script:ExpectedProfile;started=$created;verified=$true;ownerVerified=$true;sessionVerified=$true}
}
try {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { $script:Report.status='unsupported';throw 'windows_required' }
    if ($CaptureContext -cnotin @('fixture','startup-diagnostic')) { throw 'capture_context_invalid' }
    if ($args.Count -ne 0 -or -not [int]::TryParse($PidValue,[ref]$script:OwnedPid) -or $script:OwnedPid -le 1) { throw 'invalid_pid' }
    if ($ExpectedStarted -cnotmatch '^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{7}Z$') { throw 'exact_creation_identity_required' }
    $script:ExpectedProfile=Canonical $Profile $true
    $script:ExpectedExecutable=Canonical $Executable $false
    $outputParent=Canonical ([IO.Path]::GetDirectoryName($OutputFile)) $true
    if ([IO.Path]::GetFileName($OutputFile) -cne 'browser-window.png' -or -not [string]::Equals($outputParent,[IO.Path]::GetDirectoryName($script:ExpectedProfile),[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $OutputFile)) { throw 'exclusive_owned_output_required' }
    Add-Type -ReferencedAssemblies @('System.dll','System.Drawing.dll') -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
namespace OwnedWindowCapture {
 public static class Native {
  [StructLayout(LayoutKind.Sequential)] struct RECT { public int left,top,right,bottom; }
  [DllImport("shell32.dll",CharSet=CharSet.Unicode,ExactSpelling=true)] static extern IntPtr CommandLineToArgvW(string command,out int count);
  [DllImport("kernel32.dll")] static extern IntPtr LocalFree(IntPtr memory);
  [DllImport("user32.dll")] static extern bool IsWindow(IntPtr window);
  [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr window);
  [DllImport("user32.dll")] static extern bool IsIconic(IntPtr window);
  [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] static extern IntPtr GetWindow(IntPtr window,uint command);
  [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr window,out uint pid);
  [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr window,out RECT rect);
  [DllImport("user32.dll")] static extern uint GetDpiForWindow(IntPtr window);
  [DllImport("user32.dll")] static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
  [DllImport("user32.dll",CharSet=CharSet.Unicode,ExactSpelling=true)] static extern int GetClassNameW(IntPtr window,StringBuilder name,int maximum);
  [DllImport("user32.dll",SetLastError=true)] static extern bool PrintWindow(IntPtr window,IntPtr dc,uint flags);
  [DllImport("dwmapi.dll")] static extern int DwmGetWindowAttribute(IntPtr window,uint attribute,out uint value,uint size);
  public static string[] Parse(string command) {
   int count;var memory=CommandLineToArgvW(command,out count);
   if(memory==IntPtr.Zero)throw new InvalidOperationException("argument_parse_failed");
   try {if(count<1||count>4096)throw new InvalidOperationException("argument_count_invalid");
    var result=new string[count];for(int i=0;i<count;i++)result[i]=Marshal.PtrToStringUni(Marshal.ReadIntPtr(memory,i*IntPtr.Size));return result;
   } finally {LocalFree(memory);}
  }
  public static long[] Snapshot(long handle,int expectedPid) {
   var window=new IntPtr(handle);uint pid,cloaked;var name=new StringBuilder(256);
   if(!IsWindow(window)||GetWindowThreadProcessId(window,out pid)==0||pid!=(uint)expectedPid||!IsWindowVisible(window)||IsIconic(window)||GetForegroundWindow()!=window||GetWindow(window,4)!=IntPtr.Zero||DwmGetWindowAttribute(window,14,out cloaked,4)!=0||cloaked!=0||GetClassNameW(window,name,256)==0||name.ToString()!="Chrome_WidgetWin_1")throw new InvalidOperationException("normal_owned_foreground_window_required");
   var previous=SetThreadDpiAwarenessContext(new IntPtr(-4));if(previous==IntPtr.Zero)throw new InvalidOperationException("physical_dpi_context_unavailable");
   try {RECT rect;if(!GetWindowRect(window,out rect))throw new InvalidOperationException("window_bounds_unavailable");
    long width=(long)rect.right-rect.left,height=(long)rect.bottom-rect.top;uint dpi=GetDpiForWindow(window);
    if(width<320||height<240||width>2048||height>1536||width*height>3145728||dpi==0)throw new InvalidOperationException("window_bounds_or_dpi_unsupported");
    return new long[]{rect.left,rect.top,width,height,dpi};
   }finally{SetThreadDpiAwarenessContext(previous);}
  }
  public static int Capture(long handle,int pid,string output) {
   var previous=SetThreadDpiAwarenessContext(new IntPtr(-4));if(previous==IntPtr.Zero)throw new InvalidOperationException("physical_dpi_context_unavailable");
   try {var before=Snapshot(handle,pid);
    using(var bitmap=new Bitmap((int)before[2],(int)before[3],PixelFormat.Format32bppRgb)) {
     using(var graphics=Graphics.FromImage(bitmap)){var dc=graphics.GetHdc();try{if(!PrintWindow(new IntPtr(handle),dc,0))throw new InvalidOperationException("printwindow_failed");}finally{graphics.ReleaseHdc(dc);}}
     var after=Snapshot(handle,pid);for(int i=0;i<before.Length;i++)if(before[i]!=after[i])throw new InvalidOperationException("window_changed_during_capture");
     var colors=new Dictionary<int,bool>();for(int y=0;y<24;y++)for(int x=0;x<32;x++)colors[bitmap.GetPixel((x*bitmap.Width)/32,(y*bitmap.Height)/24).ToArgb()]=true;
     if(colors.Count<2)throw new InvalidOperationException("solid_capture_refused");
     using(var file=new FileStream(output,FileMode.CreateNew,FileAccess.Write,FileShare.None)){bitmap.Save(file,ImageFormat.Png);file.Flush(true);if(file.Length>3145728)throw new InvalidOperationException("png_size_limit");}
     return colors.Count;
    }
   }finally{SetThreadDpiAwarenessContext(previous);}
  }
 }
}
'@
    $original=Identity
    $script:Report.identity=$original
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes
    Assert-Budget
    $script:Report.nativeUiAccessed=$true
    $pidCondition=New-Object Windows.Automation.PropertyCondition([Windows.Automation.AutomationElement]::ProcessIdProperty,$script:OwnedPid)
    $typeCondition=New-Object Windows.Automation.PropertyCondition([Windows.Automation.AutomationElement]::ControlTypeProperty,[Windows.Automation.ControlType]::Window)
    $condition=New-Object Windows.Automation.AndCondition($pidCondition,$typeCondition)
    $windows=[Windows.Automation.AutomationElement]::RootElement.FindAll([Windows.Automation.TreeScope]::Children,$condition)
    if ($windows.Count -gt 8) { throw 'owned_window_limit' }
    $selected=New-Object 'System.Collections.Generic.List[object]'
    foreach ($window in $windows) {
        Assert-Budget
        $script:Report.visitedWindows++
        $current=$window.Current
        $kind=Title-Kind $current.Name
        if ($current.ProcessId -ne $script:OwnedPid -or $current.IsOffscreen -or $null -eq $kind) { continue }
        $pattern=$null
        if (-not $window.TryGetCurrentPattern([Windows.Automation.WindowPattern]::Pattern,[ref]$pattern) -or $pattern.Current.IsModal) { continue }
        try {$bounds=[OwnedWindowCapture.Native]::Snapshot([long]$current.NativeWindowHandle,$script:OwnedPid)}catch{continue}
        $selected.Add(@{handle=[long]$current.NativeWindowHandle;bounds=$bounds;element=$window;title=$current.Name;titleKind=$kind})
    }
    if ($selected.Count -ne 1) { $script:Report.status='unsupported';throw 'unique_owned_normal_window_unavailable' }
    $fresh=Identity
    if ($fresh.started -cne $original.started) { throw 'process_changed_before_capture' }
    $fresh.immediatelyRevalidated=$true
    $script:Report.identity=$fresh
    Assert-Budget
    $chosen=$selected[0]
    Assert-WindowTitle $chosen
    $before=[OwnedWindowCapture.Native]::Snapshot($chosen.handle,$script:OwnedPid)
    $script:Report.window=@{handle=$chosen.handle.ToString('x');ownerPID=$script:OwnedPid;foregroundVerified=$true;visible=$true;minimized=$false;cloaked=$false;normalTopLevelVerified=$true;fixtureTitleVerified=($chosen.titleKind -ceq 'fixture');titleKind=$chosen.titleKind;titleContextVerified=$true;titleUnchangedAfterCapture=$false
        x=$before[0];y=$before[1];width=$before[2];height=$before[3];dpi=$before[4];unchangedAfterCapture=$false}
    $script:Report.captureAttempted=$true
    $script:Report.captureSucceeded=$null
    $script:Report.captureOutcomeUncertain=$true
    $colors=[OwnedWindowCapture.Native]::Capture($chosen.handle,$script:OwnedPid,$OutputFile)
    $final=Identity
    $after=[OwnedWindowCapture.Native]::Snapshot($chosen.handle,$script:OwnedPid)
    Assert-WindowTitle $chosen
    if ($final.started -cne $original.started -or ($before -join ',') -cne ($after -join ',')) { throw 'identity_or_window_changed_after_capture' }
    $final.immediatelyRevalidated=$true;$final.afterCaptureRevalidated=$true
    $script:Report.identity=$final
    $file=Get-Item -LiteralPath $OutputFile -Force
    if ($file.PSIsContainer -or ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $file.Length -gt 3145728) { throw 'created_png_type_or_size_invalid' }
    $script:Report.window=@{handle=$chosen.handle.ToString('x');ownerPID=$script:OwnedPid;foregroundVerified=$true;visible=$true;minimized=$false;cloaked=$false;normalTopLevelVerified=$true;fixtureTitleVerified=($chosen.titleKind -ceq 'fixture');titleKind=$chosen.titleKind;titleContextVerified=$true;titleUnchangedAfterCapture=$true
        x=$after[0];y=$after[1];width=$after[2];height=$after[3];dpi=$after[4];unchangedAfterCapture=$true}
    $script:Report.png=@{file='browser-window.png';width=$after[2];height=$after[3];bytes=$file.Length;sha256=(Get-FileHash -LiteralPath $OutputFile -Algorithm SHA256).Hash.ToLowerInvariant()}
    $script:Report.contentCheck=@{sampleCount=768;uniqueSampleColors=$colors;nonUniform=$true;visualCompletenessVerified=$false}
    $script:Report.method='PrintWindow-full-window-flags-0'
    $script:Report.captureSucceeded=$true;$script:Report.captureOutcomeUncertain=$false;$script:Report.status='captured'
}catch{
    if ($script:Report.captureAttempted) { $script:Report.status='error' }
    $exception=$_.Exception
    for ($depth=0;$depth -lt 3 -and $null -ne $exception.InnerException;$depth++) { $exception=$exception.InnerException }
    $message=$exception.Message
    if ($message -cnotmatch '^[a-z_]{1,100}$') { $message='native_capture_unavailable' }
    $script:Report.errors=@($message)
}
$text=$script:Report|ConvertTo-Json -Depth 9 -Compress
if ([Text.Encoding]::UTF8.GetByteCount($text) -gt 65536) { throw 'capture_receipt_limit' }
[Console]::WriteLine($text)
