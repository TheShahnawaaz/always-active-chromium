# Test-only native uBOL permission actions. The separate store-ui.ps1 stays read-only.
param(
    [string]$PidValue,
    [string]$Profile,
    [string]$Executable,
    [string]$ExpectedStarted,
    [string]$Target,
    [string]$Operation
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$script:Clock = [Diagnostics.Stopwatch]::StartNew()
$script:OwnedPid = 0
$script:Visited = 0
$script:Report = [ordered]@{
    schema = 1; platform = 'win32'; status = 'refused'; target = $Target
    operation = $Operation; actionAttempted = $false; actionPerformed = $false
    identity = @{ verified = $false }; prompt = @{}; errors = @()
    limits = @{ totalMs = 10000; maxNodes = 192; maxDepth = 12; maxAncestors = 16; maxOutputBytes = 65536 }
}

function Assert-Budget {
    if ($script:Clock.ElapsedMilliseconds -ge 10000) { throw 'action_budget_exceeded' }
}

function Get-CanonicalPath([string]$Value, [bool]$Directory) {
    if ([string]::IsNullOrEmpty($Value) -or -not [IO.Path]::IsPathRooted($Value) -or
        [IO.Path]::GetPathRoot($Value).Length -lt 3) { throw 'absolute_path_required' }
    $item = Get-Item -LiteralPath $Value -Force
    if ([bool]$item.PSIsContainer -ne $Directory -or $item.PSProvider.Name -ne 'FileSystem') {
        throw 'path_type_mismatch'
    }
    return [IO.Path]::GetFullPath($item.FullName).TrimEnd([IO.Path]::DirectorySeparatorChar)
}

function Get-OwnedIdentity {
    Assert-Budget
    $process = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $script:OwnedPid) -OperationTimeoutSec 3
    if ($null -eq $process -or $process.SessionId -ne [Diagnostics.Process]::GetCurrentProcess().SessionId) {
        throw 'owned_process_missing_or_wrong_session'
    }
    $owner = Invoke-CimMethod -InputObject $process -MethodName GetOwnerSid -OperationTimeoutSec 3
    if ($owner.ReturnValue -ne 0 -or $owner.Sid -ne [Security.Principal.WindowsIdentity]::GetCurrent().User.Value) {
        throw 'owned_process_owner_mismatch'
    }
    $actualExecutable = Get-CanonicalPath $process.ExecutablePath $false
    if (-not [string]::Equals($actualExecutable, $script:ExpectedExecutable, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'owned_executable_mismatch'
    }
    $started = $process.CreationDate.ToUniversalTime().ToString('o')
    if ($started -cne $ExpectedStarted) { throw 'owned_process_creation_mismatch' }
    if ([string]::IsNullOrEmpty($process.CommandLine) -or $process.CommandLine.Length -gt 131072) {
        throw 'owned_arguments_unavailable'
    }
    $arguments = [StoreNativeAction.Ownership]::Parse($process.CommandLine)
    $profiles = New-Object 'System.Collections.Generic.List[string]'
    for ($index = 0; $index -lt $arguments.Length; $index++) {
        if ($arguments[$index].StartsWith('--user-data-dir=', [StringComparison]::Ordinal)) {
            $profiles.Add($arguments[$index].Substring('--user-data-dir='.Length))
        } elseif ($arguments[$index] -ceq '--user-data-dir' -and $index + 1 -lt $arguments.Length) {
            $profiles.Add($arguments[$index + 1])
        }
    }
    if ($profiles.Count -ne 1 -or -not [string]::Equals(
        (Get-CanonicalPath $profiles[0] $true), $script:ExpectedProfile, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'owned_profile_mismatch'
    }
    return @{ pid = $script:OwnedPid; executable = $actualExecutable; profile = $script:ExpectedProfile
              started = $started; verified = $true; immediatelyRevalidated = $false }
}

function Get-Control($Element) {
    Assert-Budget
    $script:Visited++
    if ($script:Visited -gt 192) { throw 'native_node_limit_exceeded' }
    $current = $Element.Current
    if ($current.ProcessId -ne $script:OwnedPid) { throw 'foreign_native_node' }
    if ($current.ControlType -eq [Windows.Automation.ControlType]::Document -or $current.IsPassword) {
        throw 'web_or_password_subtree_refused'
    }
    $name = [string]$current.Name
    if ([Text.Encoding]::UTF8.GetByteCount($name) -gt 240) { throw 'native_string_limit_exceeded' }
    return @{ element = $Element; name = $name; role = $current.ControlType
              enabled = [bool]$current.IsEnabled; offscreen = [bool]$current.IsOffscreen
              hwnd = $current.NativeWindowHandle }
}

function Get-CurrentPrompt {
    Assert-Budget
    $focus = [Windows.Automation.AutomationElement]::FocusedElement
    if ($null -eq $focus -or $focus.Current.ProcessId -ne $script:OwnedPid) { throw 'no_owned_native_focus' }
    $walker = [Windows.Automation.TreeWalker]::RawViewWalker
    $chain = New-Object 'System.Collections.Generic.List[object]'
    $cursor = $focus
    $ownedWindow = $null
    # First verify ownership of the entire focus-to-HWND chain without reading text.
    while ($null -ne $cursor -and $chain.Count -lt 16) {
        Assert-Budget
        $current = $cursor.Current
        if ($current.ProcessId -ne $script:OwnedPid -or
            $current.ControlType -eq [Windows.Automation.ControlType]::Document) {
            throw 'native_focus_ancestry_refused'
        }
        foreach ($prior in $chain) {
            if ([Windows.Automation.Automation]::Compare($prior, $cursor)) { throw 'native_ancestry_cycle' }
        }
        $chain.Add($cursor)
        if ($current.ControlType -eq [Windows.Automation.ControlType]::Window -and
            [StoreNativeAction.Ownership]::IsUsableOwnedWindow($current.NativeWindowHandle, $script:OwnedPid)) {
            $ownedWindow = $current.NativeWindowHandle
            break
        }
        $cursor = $walker.GetParent($cursor)
    }
    if ($null -eq $ownedWindow) { throw 'no_owned_visible_foreground_native_window' }
    $dialogs = New-Object 'System.Collections.Generic.List[object]'
    foreach ($element in $chain) {
        $record = Get-Control $element
        $normalized = $record.name.Replace([char]0x201c, [char]0x22).Replace([char]0x201d, [char]0x22)
        if ($record.role -eq [Windows.Automation.ControlType]::Window -and $normalized -ceq $script:Heading) {
            if (-not $record.enabled -or $record.offscreen) { throw 'native_dialog_unavailable' }
            $dialogs.Add($element)
        }
    }
    if ($dialogs.Count -ne 1) { throw 'native_target_dialog_not_unique' }
    $records = New-Object 'System.Collections.Generic.List[object]'
    $seen = New-Object 'System.Collections.Generic.List[object]'
    $queue = New-Object 'System.Collections.Generic.Queue[object]'
    $queue.Enqueue(@{ element = $dialogs[0]; depth = 0 })
    while ($queue.Count -gt 0) {
        Assert-Budget
        $node = $queue.Dequeue()
        foreach ($prior in $seen) {
            if ([Windows.Automation.Automation]::Compare($prior, $node.element)) { throw 'native_dialog_cycle' }
        }
        $seen.Add($node.element)
        $record = Get-Control $node.element
        $records.Add($record)
        $child = $walker.GetFirstChild($node.element)
        if ($null -ne $child -and $node.depth -ge 12) { throw 'native_dialog_depth_incomplete' }
        while ($null -ne $child) {
            Assert-Budget
            if ($queue.Count + $script:Visited -ge 192) { throw 'native_dialog_node_limit_incomplete' }
            $queue.Enqueue(@{ element = $child; depth = $node.depth + 1 })
            $child = $walker.GetNextSibling($child)
        }
    }
    $buttons = @($records | Where-Object { $_.role -eq [Windows.Automation.ControlType]::Button })
    $affirmative = @($buttons | Where-Object { $_.name -ceq $script:Affirmative })
    $cancel = @($buttons | Where-Object { $_.name -ceq 'Cancel' })
    if ($affirmative.Count -ne 1 -or $cancel.Count -ne 1 -or
        -not $affirmative[0].enabled -or $affirmative[0].offscreen -or
        -not $cancel[0].enabled -or $cancel[0].offscreen) { throw 'native_controls_not_unique_enabled_visible' }
    $proof = @{ nativeDialogVerified = $true; targetMatched = $true
                heading = $script:Heading; affirmativeLabel = $script:Affirmative
                affirmativeEnabled = $true; affirmativeUnique = $true
                nativeWindowHandle = $ownedWindow; dialogTraversalComplete = $true }
    if ($Operation -ceq 'accept-install') {
        $permission = @($records | Where-Object { $_.name -ceq 'Read and change all your data on all websites' })
        if ($permission.Count -lt 1) { throw 'observed_install_permission_text_missing' }
        $proof.permissionTextMatched = $true
    } else {
        $checkboxes = @($records | Where-Object { $_.role -eq [Windows.Automation.ControlType]::CheckBox })
        $namedReport = @($records | Where-Object { $_.name -ceq 'Report abuse' })
        if ($checkboxes.Count -gt 1 -or $namedReport.Count -ne $checkboxes.Count) {
            throw 'removal_checkbox_ambiguous_or_unexpected'
        }
        if ($checkboxes.Count -eq 1) {
            if ($checkboxes[0].name -cne 'Report abuse' -or $checkboxes[0].offscreen) { throw 'removal_checkbox_unverified' }
            $toggle = $null
            if (-not $checkboxes[0].element.TryGetCurrentPattern([Windows.Automation.TogglePattern]::Pattern, [ref]$toggle) -or
                ([Windows.Automation.TogglePattern]$toggle).Current.ToggleState -ne [Windows.Automation.ToggleState]::Off) {
                throw 'report_abuse_not_known_unchecked'
            }
        }
        $proof.reportAbuseUncheckedOrAbsent = $true
        $proof.reportAbuseCheckboxPresent = $checkboxes.Count -eq 1
    }
    $invoke = $null
    if (-not $affirmative[0].element.TryGetCurrentPattern([Windows.Automation.InvokePattern]::Pattern, [ref]$invoke)) {
        throw 'native_invoke_pattern_unavailable'
    }
    return @{ element = $affirmative[0].element; invoke = $invoke; proof = $proof; dialog = $dialogs[0] }
}

try {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'windows_required' }
    if ($args.Count -ne 0 -or $Target -cne 'ubol' -or $Operation -cnotin @('accept-install', 'confirm-remove')) {
        throw 'action_target_or_operation_not_allowlisted'
    }
    if (-not [int]::TryParse($PidValue, [ref]$script:OwnedPid) -or $script:OwnedPid -le 1) { throw 'invalid_pid' }
    if ([string]::IsNullOrEmpty($ExpectedStarted) -or $ExpectedStarted.Length -gt 60 -or
        $ExpectedStarted -cnotmatch '^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{7}Z$') { throw 'exact_creation_identity_required' }
    $script:ExpectedExecutable = Get-CanonicalPath $Executable $false
    $script:ExpectedProfile = Get-CanonicalPath $Profile $true
    $script:Heading = $(if ($Operation -ceq 'accept-install') { 'Add "uBlock Origin Lite"?' } else { 'Remove "uBlock Origin Lite"?' })
    $script:Affirmative = $(if ($Operation -ceq 'accept-install') { 'Add extension' } else { 'Remove' })
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace StoreNativeAction {
    public static class Ownership {
        [DllImport("shell32.dll", CharSet = CharSet.Unicode, ExactSpelling = true, SetLastError = true)]
        private static extern IntPtr CommandLineToArgvW([MarshalAs(UnmanagedType.LPWStr)] string commandLine, out int count);
        [DllImport("kernel32.dll")] private static extern IntPtr LocalFree(IntPtr memory);
        [DllImport("user32.dll")] private static extern bool IsWindow(IntPtr window);
        [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr window);
        [DllImport("user32.dll")] private static extern bool IsIconic(IntPtr window);
        [DllImport("user32.dll")] private static extern IntPtr GetForegroundWindow();
        [DllImport("user32.dll")] private static extern bool IsChild(IntPtr parent, IntPtr child);
        [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);
        public static bool IsUsableOwnedWindow(int window, int expectedPid) {
            if (window == 0) return false;
            uint actualPid;
            var handle = new IntPtr(window);
            var foreground = GetForegroundWindow();
            return IsWindow(handle) && IsWindowVisible(handle) && !IsIconic(handle) &&
                GetWindowThreadProcessId(handle, out actualPid) != 0 && actualPid == (uint)expectedPid &&
                (foreground == handle || IsChild(handle, foreground));
        }
        public static string[] Parse(string commandLine) {
            int count;
            IntPtr memory = CommandLineToArgvW(commandLine, out count);
            if (memory == IntPtr.Zero) throw new InvalidOperationException("argument_parse_failed");
            try {
                if (count < 1 || count > 4096) throw new InvalidOperationException("argument_count_invalid");
                var result = new string[count];
                for (int i = 0; i < count; ++i) result[i] = Marshal.PtrToStringUni(Marshal.ReadIntPtr(memory, i * IntPtr.Size));
                return result;
            } finally { LocalFree(memory); }
        }
    }
}
'@
    $script:Report.identity = Get-OwnedIdentity
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes
    $initial = Get-CurrentPrompt
    # Reacquire the live native controls; a saved observer JSON cannot select an action.
    $current = Get-CurrentPrompt
    if (-not [Windows.Automation.Automation]::Compare($initial.dialog, $current.dialog) -or
        -not [Windows.Automation.Automation]::Compare($initial.element, $current.element)) { throw 'native_prompt_changed' }
    $identity = Get-OwnedIdentity
    $identity.immediatelyRevalidated = $true
    $script:Report.identity = $identity
    if (-not [StoreNativeAction.Ownership]::IsUsableOwnedWindow($current.proof.nativeWindowHandle, $script:OwnedPid)) {
        throw 'native_window_changed_before_action'
    }
    Assert-Budget
    $script:Report.prompt = $current.proof
    $script:Report.actionType = 'UIA.Invoke'
    $script:Report.actionAttempted = $true
    ([Windows.Automation.InvokePattern]$current.invoke).Invoke()
    $script:Report.actionPerformed = $true
    $script:Report.status = 'acted'
} catch {
    # Invocation errors can occur after the browser received the action.
    if ($script:Report.actionAttempted) {
        $script:Report.status = 'error'
        $script:Report.actionPerformed = $null
        $script:Report.actionOutcomeUncertain = $true
    }
    $message = [string]$_.Exception.Message
    $script:Report.errors = @($(if ($message -cmatch '^[a-z_]{1,100}$') { $message } else { 'native_action_query_or_invoke_failed' }))
}
$script:Report.visitedNodes = $script:Visited
$script:Report.elapsedMs = $script:Clock.ElapsedMilliseconds
$json = ConvertTo-Json -InputObject $script:Report -Depth 8 -Compress
if ([Text.Encoding]::UTF8.GetByteCount($json) + 1 -gt 65536) {
    $json = '{"schema":1,"status":"error","actionPerformed":null,"actionOutcomeUncertain":true,"errors":["action_serialization_limit"]}'
}
[Console]::Out.WriteLine($json)
exit 0
