# Read-only native UI prerequisite probe. Never invokes controls or changes permissions.
# powershell.exe -NoProfile -NonInteractive -File tests/ui/store-ui.ps1 `
#   -PidValue PID -Profile ABSOLUTE_PATH -Executable ABSOLUTE_PATH
# Optional: -Mode dialog observes owned focused UI without accepting a dialog.
param(
    [string]$PidValue = $env:AA_STORE_PID,
    [string]$Profile = $env:AA_STORE_PROFILE,
    [string]$Executable = $env:AA_STORE_EXECUTABLE,
    [string]$Mode = 'preflight'
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$script:MaxNodes = 128
$script:MaxDepth = 8
$script:MaxWindows = 8
$script:MaxStringBytes = 240
$script:MaxOutputBytes = 65536
$script:MaxAncestorDepth = 16
$script:Truncated = $false
$script:Visited = 0
$script:OwnedPid = 0
$script:Clock = [Diagnostics.Stopwatch]::StartNew()
$script:Report = [ordered]@{
    schema = 1
    platform = 'win32'
    purpose = 'owned-browser-native-ui-prerequisites'
    status = 'error'
    identity = @{ verified = $false }
    accessibility = @{ trusted = $null; available = $false }
    windows = @()
    errors = @()
    limits = @{ maxNodes = $script:MaxNodes; maxDepth = $script:MaxDepth
                maxWindows = $script:MaxWindows; maxStringBytes = $script:MaxStringBytes
                maxOutputBytes = $script:MaxOutputBytes; traversalBudgetMs = 8000 }
}

function Get-BoundedString([string]$Value) {
    if ($Value.Length -gt $script:MaxStringBytes) {
        $script:Truncated = $true
        $Value = $Value.Substring(0, $script:MaxStringBytes)
    }
    $clean = [regex]::Replace([string]$Value, '\p{Cc}', ' ')
    if ([Text.Encoding]::UTF8.GetByteCount($clean) -le $script:MaxStringBytes) { return $clean }
    $script:Truncated = $true
    $length = [Math]::Min($clean.Length, $script:MaxStringBytes)
    while ($length -gt 0 -and [Text.Encoding]::UTF8.GetByteCount($clean.Substring(0, $length)) -gt $script:MaxStringBytes) {
        $length--
    }
    if ($length -gt 0 -and [char]::IsHighSurrogate($clean[$length - 1])) { $length-- }
    return $clean.Substring(0, $length)
}

function Assert-Budget {
    if ($script:Clock.ElapsedMilliseconds -ge 8000) {
        $script:Truncated = $true
        throw 'traversal_deadline'
    }
}

function Get-CanonicalPath([string]$Value, [bool]$Directory) {
    if ([string]::IsNullOrEmpty($Value) -or -not [IO.Path]::IsPathRooted($Value) -or
        [IO.Path]::GetPathRoot($Value).Length -lt 3) {
        throw 'absolute_paths_required'
    }
    $item = Get-Item -LiteralPath $Value -Force
    if ([bool]$item.PSIsContainer -ne $Directory -or $item.PSProvider.Name -ne 'FileSystem') {
        throw 'expected_path_type_missing'
    }
    $full = [IO.Path]::GetFullPath($item.FullName)
    if ($full.Length -gt [IO.Path]::GetPathRoot($full).Length) {
        $full = $full.TrimEnd([IO.Path]::DirectorySeparatorChar)
    }
    return $full
}

function Get-OwnedIdentity([switch]$Final) {
    if (-not $Final) { Assert-Budget }
    # Query only the supplied PID; never enumerate other applications.
    $process = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $script:OwnedPid) -OperationTimeoutSec 3
    if ($null -eq $process) { throw 'process_missing' }
    if ($process.SessionId -ne [Diagnostics.Process]::GetCurrentProcess().SessionId) {
        throw 'process_session_mismatch'
    }
    if (-not $Final) {
        $owner = Invoke-CimMethod -InputObject $process -MethodName GetOwnerSid -OperationTimeoutSec 3
        if ($owner.ReturnValue -ne 0 -or $owner.Sid -ne [Security.Principal.WindowsIdentity]::GetCurrent().User.Value) {
            throw 'process_owner_mismatch'
        }
    }
    $actualExecutable = Get-CanonicalPath $process.ExecutablePath $false
    if (-not [string]::Equals($actualExecutable, $script:ExpectedExecutable, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'process_executable_mismatch'
    }
    if ([string]::IsNullOrEmpty($process.CommandLine) -or $process.CommandLine.Length -gt 131072) {
        throw 'process_arguments_unavailable_or_oversized'
    }
    $arguments = [StoreUIReadOnly.NativeArguments]::Parse($process.CommandLine)
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
        throw 'process_profile_mismatch'
    }
    return @{ pid = $script:OwnedPid; executable = $actualExecutable; profile = $script:ExpectedProfile
              created = $process.CreationDate.ToUniversalTime().ToString('o'); verified = $true }
}

function Get-ControlSnapshot($Element, [int]$Depth, [switch]$Detailed) {
    Assert-Budget
    if ($script:Visited -ge $script:MaxNodes) { $script:Truncated = $true; return $null }
    $script:Visited++
    $current = $Element.Current
    # Foreign process nodes below a browser window are never inspected further.
    if ($current.ProcessId -ne $script:OwnedPid) { return $null }
    $record = @{ role = Get-BoundedString $current.ControlType.ProgrammaticName
                 title = Get-BoundedString $current.Name
                 enabled = [bool]$current.IsEnabled; offscreen = [bool]$current.IsOffscreen
                 depth = $Depth }
    if ($Detailed) {
        $record.subrole = Get-BoundedString $current.LocalizedControlType
        $record.description = Get-BoundedString $current.HelpText
        $record.value = $null
        if ($current.IsPassword) { $record.valueRedacted = $true }
        else {
            # Read-only patterns: never invoke, focus, set a value, or select text.
            try {
                $pattern = $null
                Assert-Budget
                if ($Element.TryGetCurrentPattern([Windows.Automation.ValuePattern]::Pattern, [ref]$pattern)) {
                    $record.value = Get-BoundedString (([Windows.Automation.ValuePattern]$pattern).Current.Value)
                } else {
                    $pattern = $null
                    Assert-Budget
                    if ($Element.TryGetCurrentPattern([Windows.Automation.TextPattern]::Pattern, [ref]$pattern)) {
                        $record.value = Get-BoundedString (([Windows.Automation.TextPattern]$pattern).DocumentRange.GetText($script:MaxStringBytes))
                    }
                }
            } catch { $record.valueReadUnavailable = $true }
        }
    }
    return $record
}

function Get-DialogInspection {
    $result = @{ status = 'not-found'; focused = $null; ancestors = @(); containers = @()
                 promptIdentityVerified = $false; notes = @(); truncated = $false
                 maxAncestorDepth = $script:MaxAncestorDepth }
    try {
        Assert-Budget
        $focused = [Windows.Automation.AutomationElement]::FocusedElement
        # Reading the PID is the only operation on an unverified focus object.
        if ($null -eq $focused -or $focused.Current.ProcessId -ne $script:OwnedPid) {
            $result.notes = @('no_owned_focused_element')
            return $result
        }
        $walker = [Windows.Automation.TreeWalker]::RawViewWalker
        $chain = New-Object 'System.Collections.Generic.List[object]'
        $cursor = $focused
        $windowVerified = $false
        while ($null -ne $cursor -and $chain.Count -lt $script:MaxAncestorDepth -and $script:Visited -lt $script:MaxNodes) {
            Assert-Budget
            $script:Visited++
            $current = $cursor.Current
            if ($current.ProcessId -ne $script:OwnedPid) { break }
            $duplicate = $false
            foreach ($prior in $chain) {
                if ([Windows.Automation.Automation]::Compare($prior, $cursor)) { $duplicate = $true; break }
            }
            if ($duplicate) { break }
            $chain.Add($cursor)
            if ($current.ControlType -eq [Windows.Automation.ControlType]::Window -and
                [StoreUIReadOnly.NativeArguments]::IsOwnedWindow($current.NativeWindowHandle, $script:OwnedPid)) {
                $windowVerified = $true
                break
            }
            $cursor = $walker.GetParent($cursor)
        }
        if (-not $windowVerified) {
            $result.notes = @('focused_element_has_no_verified_owned_window_ancestry')
            if ($chain.Count -ge $script:MaxAncestorDepth -or $script:Visited -ge $script:MaxNodes) { $script:Truncated = $true }
            $result.truncated = $script:Truncated
            return $result
        }
        # Only now inspect text/value beneath a verified, same-PID native window.
        $records = New-Object 'System.Collections.Generic.List[object]'
        for ($index = 0; $index -lt $chain.Count; $index++) {
            $record = Get-ControlSnapshot ($chain[$index]) $index -Detailed
            if ($null -eq $record) { throw 'focused_chain_snapshot_incomplete' }
            $record.windowOwnershipVerified = $true
            $records.Add($record)
        }
        $windowRecord = $records[$records.Count - 1].Clone()
        $windowRecord.windowRoleVerified = $true
        $windowRecord.nativeWindowOwnershipVerified = $true
        $windowRecord.nativeWindowHandle = $chain[$chain.Count - 1].Current.NativeWindowHandle
        $result.focused = $records[0]
        $result.ancestors = @($records | Select-Object -Skip 1)
        $result.window = $windowRecord
        $result.status = 'observed'
        $result.notes = @('owned_focused_ui_only_not_a_verified_install_prompt')

        # Observe a few nearby ancestors plus the window; do not assume a role
        # or title identifies the extension prompt before actual capture.
        $selected = New-Object 'System.Collections.Generic.List[int]'
        if ($chain.Count -gt 1) { $selected.Add(1) }
        if ($chain.Count -gt 2) { $selected.Add(2) }
        if ($chain.Count -gt 3) { $selected.Add(3) }
        if (-not $selected.Contains($chain.Count - 1)) { $selected.Add($chain.Count - 1) }
        $containers = New-Object 'System.Collections.Generic.List[object]'
        foreach ($index in $selected) {
            $record = $records[$index].Clone()
            $record.selectionReason = $(if ($index -eq $chain.Count - 1) { 'verified_focused_window' } else { 'near_focused_ancestor' })
            $controls = New-Object 'System.Collections.Generic.List[object]'
            $queue = New-Object 'System.Collections.Generic.Queue[object]'
            $queue.Enqueue(@{ element = $chain[$index]; depth = 0 })
            try {
                while ($queue.Count -gt 0 -and $script:Visited -lt $script:MaxNodes) {
                    Assert-Budget
                    $node = $queue.Dequeue()
                    if ($node.depth -ge $script:MaxDepth) { $script:Truncated = $true; continue }
                    $child = $walker.GetFirstChild($node.element)
                    while ($null -ne $child -and $script:Visited -lt $script:MaxNodes) {
                        $childRecord = Get-ControlSnapshot $child ($node.depth + 1) -Detailed
                        if ($null -ne $childRecord) {
                            $childRecord.windowOwnershipVerified = $true
                            $controls.Add($childRecord)
                            $queue.Enqueue(@{ element = $child; depth = $node.depth + 1 })
                        }
                        Assert-Budget
                        $child = $walker.GetNextSibling($child)
                    }
                    if ($null -ne $child) { $script:Truncated = $true }
                }
                if ($queue.Count -gt 0) { $script:Truncated = $true }
            } catch {
                $script:Truncated = $true
                $result.notes = @((Get-BoundedString $_.Exception.Message))
            }
            $record.controls = $controls.ToArray()
            $containers.Add($record)
            $result.containers = $containers.ToArray()
            if ($script:Visited -ge $script:MaxNodes -or $script:Clock.ElapsedMilliseconds -ge 8000) { break }
        }
    } catch {
        $result.status = 'error'
        $result.notes = @((Get-BoundedString $_.Exception.Message))
    }
    $result.truncated = $script:Truncated
    return $result
}

try {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        $script:Report.status = 'unsupported'
        throw 'windows_required'
    }
    if ($args.Count -ne 0) { throw 'invalid_arguments' }
    if ($Mode -cnotin @('preflight', 'dialog')) { throw 'invalid_mode' }
    if ($Mode -ceq 'dialog') { $script:Report.mode = $Mode }
    if (-not [int]::TryParse($PidValue, [ref]$script:OwnedPid) -or $script:OwnedPid -le 1) {
        throw 'invalid_pid'
    }
    $script:ExpectedProfile = Get-CanonicalPath $Profile $true
    $script:ExpectedExecutable = Get-CanonicalPath $Executable $false
    # These APIs only parse the already selected process's command line.
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace StoreUIReadOnly {
    public static class NativeArguments {
        [DllImport("shell32.dll", CharSet = CharSet.Unicode, ExactSpelling = true, SetLastError = true)]
        private static extern IntPtr CommandLineToArgvW([MarshalAs(UnmanagedType.LPWStr)] string commandLine, out int count);
        [DllImport("kernel32.dll")]
        private static extern IntPtr LocalFree(IntPtr memory);
        [DllImport("user32.dll")]
        private static extern bool IsWindow(IntPtr window);
        [DllImport("user32.dll")]
        private static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);
        public static bool IsOwnedWindow(int window, int expectedPid) {
            if (window == 0) return false;
            uint actualPid;
            var handle = new IntPtr(window);
            return IsWindow(handle) && GetWindowThreadProcessId(handle, out actualPid) != 0 && actualPid == (uint)expectedPid;
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
    $original = Get-OwnedIdentity
    $script:Report.identity = $original
    # Do not load or query UI Automation until executable/profile/owner are verified.
    try {
        Add-Type -AssemblyName UIAutomationClient
        Add-Type -AssemblyName UIAutomationTypes
    } catch {
        $script:Report.status = 'unsupported'
        throw 'ui_automation_unavailable'
    }
    Assert-Budget
    $condition = New-Object System.Windows.Automation.PropertyCondition(
        [Windows.Automation.AutomationElement]::ProcessIdProperty, $script:OwnedPid)
    $ownedWindows = [Windows.Automation.AutomationElement]::RootElement.FindAll(
        [Windows.Automation.TreeScope]::Children, $condition)
    $walker = [Windows.Automation.TreeWalker]::RawViewWalker
    $windows = New-Object 'System.Collections.Generic.List[object]'
    if ($ownedWindows.Count -gt $script:MaxWindows) { $script:Truncated = $true }
    $dialogWindowRecords = @{}
    if ($Mode -ceq 'dialog') {
        # Preserve real window observations before detailed inspection uses the
        # shared node budget. The default preflight traversal is unchanged.
        for ($index = 0; $index -lt [Math]::Min($ownedWindows.Count, $script:MaxWindows); $index++) {
            $record = Get-ControlSnapshot ($ownedWindows.Item($index)) 0
            if ($null -ne $record) { $dialogWindowRecords[$index] = $record }
        }
        $script:Report.dialogInspection = Get-DialogInspection
    }
    for ($windowIndex = 0; $windowIndex -lt [Math]::Min($ownedWindows.Count, $script:MaxWindows); $windowIndex++) {
        $window = $ownedWindows.Item($windowIndex)
        if ($Mode -ceq 'dialog') { $record = $dialogWindowRecords[$windowIndex] }
        else { $record = Get-ControlSnapshot $window 0 }
        if ($null -eq $record) { continue }
        $controls = New-Object 'System.Collections.Generic.List[object]'
        $queue = New-Object 'System.Collections.Generic.Queue[object]'
        $queue.Enqueue(@{ element = $window; depth = 0 })
        try {
            while ($Mode -ceq 'preflight' -and $queue.Count -gt 0 -and $script:Visited -lt $script:MaxNodes) {
                Assert-Budget
                $node = $queue.Dequeue()
                if ($node.depth -ge $script:MaxDepth) { $script:Truncated = $true; continue }
                $child = $walker.GetFirstChild($node.element)
                while ($null -ne $child -and $script:Visited -lt $script:MaxNodes) {
                    $childRecord = Get-ControlSnapshot $child ($node.depth + 1)
                    if ($null -ne $childRecord) {
                        $controls.Add($childRecord)
                        $queue.Enqueue(@{ element = $child; depth = $node.depth + 1 })
                    }
                    Assert-Budget
                    $child = $walker.GetNextSibling($child)
                }
                if ($null -ne $child) { $script:Truncated = $true }
            }
            if ($Mode -ceq 'preflight' -and $queue.Count -gt 0) { $script:Truncated = $true }
        } catch {
            $script:Truncated = $true
            $script:Report.errors = @((Get-BoundedString $_.Exception.Message))
        }
        $record.controls = $controls.ToArray()
        $windows.Add($record)
        $script:Report.windows = $windows.ToArray()
        if ($script:Clock.ElapsedMilliseconds -ge 8000 -or $script:Visited -ge $script:MaxNodes) { break }
    }
    # Recheck PID creation identity after cross-process accessibility calls.
    try {
        $final = Get-OwnedIdentity -Final
        if ($original.created -ne $final.created) { throw 'process_identity_changed_during_probe' }
    } catch {
        $script:Report.identity = @{ pid = $script:OwnedPid; verified = $false }
        $script:Report.windows = @()
        $script:Report.Remove('dialogInspection')
        throw 'process_identity_unavailable_or_changed_during_probe'
    }
    $script:Report.visitedNodes = $script:Visited
    $script:Report.accessibility.available = $windows.Count -gt 0
    $visible = @($windows | Where-Object { -not $_.offscreen })
    if ($visible.Count -gt 0) { $script:Report.status = 'ready' }
    else {
        $script:Report.status = 'unsupported'
        $script:Report.errors = @('no_owned_visible_accessible_window')
    }
} catch {
    if ($script:Report.status -ne 'unsupported') { $script:Report.status = 'error' }
    $script:Report.errors = @((Get-BoundedString $_.Exception.Message))
}
$script:Report.truncated = $script:Truncated
# Bound the encoded output as well as the tree and individual strings.
while ($true) {
    $json = ConvertTo-Json -InputObject $script:Report -Depth 16 -Compress
    if ([Text.Encoding]::UTF8.GetByteCount($json) + 1 -le $script:MaxOutputBytes) { break }
    $script:Report.truncated = $true
    $windows = @($script:Report.windows)
    $reduced = $false
    for ($index = $windows.Count - 1; $index -ge 0; $index--) {
        $controls = @($windows[$index].controls)
        if ($controls.Count -gt 0) {
            $windows[$index].controls = @($controls | Select-Object -First ($controls.Count - 1))
            $reduced = $true
            break
        }
    }
    if (-not $reduced -and $windows.Count -gt 0) {
        $windows = @($windows | Select-Object -First ($windows.Count - 1))
        $reduced = $true
    }
    $script:Report.windows = $windows
    if (-not $reduced -and $null -ne $script:Report.dialogInspection) {
        $inspection = $script:Report.dialogInspection
        $containers = @($inspection.containers)
        for ($index = $containers.Count - 1; $index -ge 0; $index--) {
            $controls = @($containers[$index].controls)
            if ($controls.Count -gt 0) {
                $containers[$index].controls = @($controls | Select-Object -First ($controls.Count - 1))
                $reduced = $true
                break
            }
        }
        if (-not $reduced -and $containers.Count -gt 0) {
            $containers = @($containers | Select-Object -First ($containers.Count - 1))
            $reduced = $true
        } elseif (-not $reduced -and @($inspection.ancestors).Count -gt 0) {
            $inspection.ancestors = @($inspection.ancestors | Select-Object -First (@($inspection.ancestors).Count - 1))
            $reduced = $true
        }
        $inspection.containers = $containers
        $inspection.truncated = $true
        $script:Report.dialogInspection = $inspection
    }
    if (-not $reduced) {
        $json = '{"schema":1,"platform":"win32","status":"error","errors":["serialization_failed"]}'
        break
    }
}
[Console]::Out.WriteLine($json)
exit 0
