# Native Store action helper contract

`store-compat.mjs` requires `AA_STORE_ACTION_HELPER` independently of the
read-only `AA_STORE_UI_HELPER`. The controller's target is fixed to audited
uBlock Origin Lite. Helpers and controller require joint review before a real
installation run. A helper path existing on disk does not establish readiness.

Windows invocation:

```text
powershell.exe -NoProfile -NonInteractive -File ACTION.ps1
  -PidValue PID -Profile ABS -Executable ABS -ExpectedStarted EXACT_CIM_ISO
  -Target ubol -Operation accept-install|confirm-remove
```

macOS invocation:

```text
ACTION --pid PID --profile ABS --executable ABS --expected-started PS_LSTART
  --expected-start-seconds N --expected-start-microseconds N
  --target ubol --operation accept-install|confirm-remove
```

The Mac precise creation fields come from the fresh same-PID native probe's
`proc_pidinfo` seconds/microseconds, not a conversion of second-resolution ps
text. `identity.started` returns the supplied normalized launch identity for
report matching, while the precise native fields must also match. Windows uses
the exact seven-fraction-digit CIM creation string.

Mac actions additionally require finite positive current native AXPosition and
AXSize bounds for both buttons inside the active, nonhidden, nonminimized owning
window. They must also fit inside the native sheet when its bounds are exposed.
Missing mandatory or partially exposed bounds refuse the action; no coordinate
input fallback is used.

Before acting, prove the exact PID/executable/profile, process owner/session,
and creation identity. Reacquire the entire target-specific native dialog after
that identity check, including permission text or checkbox state, immediately
before one supported native control action. Require a unique enabled visible
affirmative control and Cancel inside the same verified native dialog/window;
web content, old snapshots, app-name-only targeting, global Enter, private
installation APIs and privileged uninstall calls are excluded.

For installation, actual hosted uBOL captures on both platforms established
`Add "uBlock Origin Lite"?`, native Add extension/Cancel, and the permission
`Read and change all your data on all websites`. The helper must freshly match
those observed target-specific fields. For removal, exact .80 source defines
`Remove "uBlock Origin Lite"?`, Remove/Cancel and optional Report abuse.
Source text is insufficient proof that a removal prompt exists: inspect the
actual current native target and require the abuse checkbox to be known Off or
absent before confirming. Unknown, checked, unexpected or ambiguous checkbox
state must refuse the action.

A successful JSON receipt is bounded to 64 KiB:

```json
{
  "schema": 1,
  "status": "acted",
  "operation": "accept-install",
  "target": "ubol",
  "actionAttempted": true,
  "actionPerformed": true,
  "actionOutcomeUncertain": false,
  "actionType": "UIA.Invoke",
  "identity": {
    "pid": 123,
    "executable": "ABS",
    "profile": "ABS",
    "started": "EXACT_LAUNCH_CREATION_IDENTITY",
    "verified": true,
    "immediatelyRevalidated": true
  },
  "prompt": {
    "nativeDialogVerified": true,
    "targetMatched": true,
    "affirmativeLabel": "Add extension",
    "affirmativeEnabled": true,
    "affirmativeUnique": true,
    "permissionTextMatched": true
  }
}
```

Mac success uses `actionType:"AXPress"` and includes numeric `startSeconds` and
`startMicroseconds` in `identity`. For removal, the affirmative label is Remove
and `prompt.reportAbuseUncheckedOrAbsent:true` is mandatory. A supported verified
native mouse action may report `native-mouse-click` if separately implemented
and reviewed. Successful action acknowledgment is not installation/removal
proof; the controller separately observes the target registry and restart.

`status` may instead be `refused` or `error`. Only a complete matching receipt
with `actionAttempted:false`, `actionPerformed:false` and no uncertainty flag
establishes that no native action occurred. After invoking a synchronous native
method, any exception/timeout/transport loss may have an uncertain outcome;
return null for an unknown `actionPerformed` and mark uncertainty explicitly.
The controller applies a 15-second hard process timeout with SIGKILL, treats
missing/incomplete receipts as uncertain, and never automatically retries an
uncertain native action. It attempts a read-only registry observation without
focus/navigation changes and then closes only its owned browser.
