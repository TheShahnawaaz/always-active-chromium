# Normal Store compatibility test preparation

Status: reviewed CFT reference runs on both platforms have observed normal uBOL
installation, source verification, execution, restart persistence, one update
check, native removal and post-removal restart absence. The final reference run
of the corrected persisted-registration check remains pending. Actual native
browser packages and a genuine newer Store version transition remain unverified.
The separate
`store-dialog.mjs` inspection contract remains read-only after clicking Store
Add: it must never acquire an acceptance action.

The planned test runs first on original CFT to validate mechanics, then on each
actual built macOS arm64 and Windows x64 package. Reference-browser results
cannot establish native-browser success.

## Audited second extension

| Field | Value |
| --- | --- |
| Name | uBlock Origin Lite |
| Store ID | `ddkjiahejlhfcafbddmgiahcphecmpfh` |
| Listing | <https://chromewebstore.google.com/detail/ublock-origin-lite/ddkjiahejlhfcafbddmgiahcphecmpfh> |
| Audited version | `2026.1026.1812` |
| Manifest | MV3; minimum Chrome `122.0`; module worker `/js/background.js` |
| Normal options page | `dashboard.html` |
| Official update URL | `https://clients2.google.com/service/update2/crx` |
| Original CRX SHA-256 | `6763ff30cb7b89bf3b411908c03674b5d4e98c12a38fbae776fd057d1a8d1837` |
| Extracted ZIP SHA-256 | `811fe48326b9b92deabce0b54f377322652f5fd5a5a7f285180fc6a508cfe5ab` |

The sibling private archive `rea-ubol-compat-2026-11-02` contains provenance,
the shipped artifact, and selected-source REA summary
`ev_9284b7f0526f6f2f6a413d41dcdf1188322f908aab2d389be9f947a082eb6a3f`
for parent `ev_7f10d3e00f984d89c3f94677850e97dd844c73bba43bcc590259b332dd21c84c`.
This is partial static evidence: four JavaScript files parsed, no parse
failures, 619 inventoried files unselected, and semantic limits reached. The
parent is not retained in the current worker's REA session. No complete security
audit or runtime execution is implied. Do not publish the extension package or
source as browser test evidence.

Normal Store installation may offer a newer version. Record the actual installed
version and compare the installed manifest/selected source digests with the
audited artifact before applying version-specific functional assertions. An
unexpected version requires a fresh bounded audit; do not silently treat the
old artifact as the installed one or pin installation through a private API.

## Reusable boundaries

- Reuse `lib/cdp.mjs`, `storeOperation`, exact owned-PID/profile/executable/start
  identity checks, the minimal Store launcher, and verified bounded cleanup.
  Keep normal flags: no unsafe extension debugging, auto-confirm, load-extension,
  background-network suppression, policies, security changes, or emulation.
- Extract parameterized, test-only DOM observation, ordinary target scrolling,
  Input mouse dispatch, and prompt-validation functions only when implementing
  the separate controller. Preserve `store-dialog.mjs` behavior and fixed target.
- Keep native read-only observers separate from a future **action helper**.
  The observer's `observed` status and a saved JSON snapshot cannot authorize a
  native action. The existing helper under `tests/ui/` remains read-only.
- Add an explicit restart boundary. The current launcher creates a new profile
  and cannot reuse it. A restart helper must reuse only the profile it created,
  after verified root/group shutdown, with a new owned process identity and log.
  Remove only that owned profile's stale DevTools endpoint file before restart;
  do not rediscover or attach to an unrelated browser/profile.

## Planned bounded phases and assertions

1. **Fresh profile and listing.** Verify exact browser revision/provenance and
   owned process identity. Open the fixed uBOL listing, require the expected
   name/ID and successful document response, confirm the target is absent, and
   require strict native UI prerequisites. Retain finite DOM/AX summaries.
2. **Normal Store Add.** Observe the actual enabled, visible Add button. Allow
   one ordinary scroll of that exact node, then recheck current viewport,
   pointer events, and hit target. Dispatch only normal mouse move/press/release
   to the freshly observed position. Never call Store installation APIs.
3. **Permission capture.** Wait across a bounded 45-second window. Require the
   actual native uBOL prompt, target name, permission text, and enabled native
   Add extension/Cancel controls within an owned native dialog/window subtree.
   Do not assume the Always Active prompt's text or shape applies to uBOL.
4. **Native acceptance.** A separate helper must freshly prove the exact target
   and control ownership immediately before one Add extension action. Record the
   action and subsequent prompt disappearance. An acknowledged action alone
   does not prove installation.
5. **Installed and executing.** Poll read-only target registry information for
   exact ID/name, enabled state, version, and `installType:'normal'`. Preserve
   the observed Store Add/prompt chain as provenance; `normal` alone also covers
   other CRX installs. Open the real installed options page and run the bounded
   read-only worker probe below. A registry entry or worker target alone cannot
   pass execution.
6. **Restart persistence.** Close normally, prove the owned process/group gone,
   and relaunch the same executable with only that owned profile. Require the
   same target/version/enabled/normal-install information, then repeat the real
   worker probe. No reload, unpacked installation, or reinstall may substitute
   for this restart.
7. **Ordinary update check.** Make one `runtime.requestUpdateCheck()` call from
   the installed extension's own page and retain its exact result. Interpret
   it as described below. The normal chrome://extensions Update control is an
   additional UI-path candidate, not a necessary reason to enable Developer
   mode for installation or the primary update check.
8. **Normal removal.** Open `chrome://extensions`, find the actual item for the
   fixed ID/name in its real DOM/shadow tree, and use normal mouse input on that
   item's visible enabled Remove control. Capture the owned native removal
   confirmation. A separate helper may confirm only that exact target's Remove
   button after the same immediate identity/control revalidation. Do not call
   `management.uninstall`, developerPrivate uninstall, or remove files/prefs.
9. **Removal persists.** Require the item to disappear, read-only target registry
   absence, and a normal close. Relaunch the same owned profile and require
   absence again; after normal closure, confirm persisted registration absence
   in bounded owned Preferences/Secure Preferences reads. Permit only no ID
   entry or a verified actually empty JSON dictionary, with no parse/shape
   uncertainty. Preserve `targetAbsent=false` when the empty identifier entry
   remains, separately from `targetRegistrationAbsent=true`. Nonempty or pending
   data must fail. This does not claim removal of every ID/preference byte.
   Cached files alone are not an installed registration. Do not open missing
   extension resources merely to infer absence.

Proposed controller budget: 12 minutes for all phases, with an additional
18-second final cleanup bound, smaller per-operation limits, at most 15 seconds
per native probe/action, and no unbounded retry. Installation download and one
update request each receive their own finite wait. Use separate phase status
fields: failed, not reached, and unverified must not become passing evidence.
If a later phase fails after installation, close the owned browser and report
the remaining target state; never use a privileged uninstall fallback to claim
normal removal. No existing user Chrome/profile is involved.

## Native acceptance/removal contract

The future action helper must take an allowlisted target ID/name and operation
(`accept-install` or `confirm-remove`), plus exact owned PID, executable, profile,
and creation identity. It must revalidate them immediately before acting, bound
all native queries, and refuse an inactive, hidden, minimized, ambiguous, stale,
or unverified target. Windows must additionally verify the real HWND owner.

Locate the current native dialog and its target-specific heading. Prove the
candidate button belongs to that native dialog under the owned native window,
with no web-content `AXWebArea`/document subtree serving as the permission UI.
Require the matching expected button, exact label/role, known enabled state,
and supported native action. Deduplicate overlapping observer containers so
one actual control is selected; several matching controls must fail safely.
Reacquire and recheck that same current target immediately before one AXPress
or UIA Invoke action (or an explicitly verified normal native mouse click).
Never press global Enter, reuse old coordinates, target by app name alone, or
invoke an installation/uninstallation implementation API.

For install, also require Cancel and the actual permission text. For removal,
require the target-specific removal prompt and Remove/Cancel; inspect the
report-abuse checkbox if present and require it to be unchecked. An unknown or
checked state must stop the action. Source confirms that
checking it changes the uninstall action, so the test must not submit an abuse
report. Missing or unexpected native UI is an unverified/failed phase.

The exact .80 normal removal path is `resources/extensions/service.ts`
`deleteItem()` -> the browser's own confirm-uninstall flow ->
`ui/extensions/extension_uninstall_dialog_impl.cc` -> registrar uninstall. The
controller activates the UI and never calls that internal path directly.

## Read-only worker execution probe

In the verified own-origin installed options page, first require
`location.origin === 'chrome-extension://ddkjiahejlhfcafbddmgiahcphecmpfh'`,
`chrome.runtime.id` to match, and the expected manifest/version. Then send only:

```js
await chrome.runtime.sendMessage({ what: 'getEnabledRulesets' });
```

Shipped `background.js:865` routes the message; it awaits its initialization
promise, checks the sender's origin (`background.js:383`), and handles the read at
`:451`. `ruleset-manager.js:548` returns native
`declarativeNetRequest.getEnabledRulesets()` IDs plus enabled imported-list IDs.
Run from the own extension page, not from CWS or an arbitrary website. Require a
bounded nonempty array of unique short strings, with stock IDs declared in the
verified installed manifest. In the fresh profile, no imported lists have been
created by the test. Record actual IDs; language-based defaults can add regional
lists, so do not require only the six manifest-enabled IDs. Repeat after restart.

This proves the shipped message handler and native ruleset-query API executed;
it does not alone prove that every advertising/filtering rule blocks correctly.
The test JS only reads state; the normal options page's own startup behavior is
part of the extension. Whether normal CDP can inspect this installed page
without unsafe extension flags still requires a genuine-install mechanics run.

## Update evidence and its limits

One ordinary own-extension call is a candidate for bounded update-path evidence:

```js
await chrome.runtime.requestUpdateCheck();
```

Record the Promise result `{status, version?}` without changing it. The pinned
schema defines `no_update`, `update_available`, and `throttled`; disabled
autoupdate rejects. `no_update` records normal check completion and **no observed
upgrade**. `update_available` records an available version, not its installation.
`throttled`, rejection, timeout, or renderer/context loss cannot pass a completed
update check. Do not loop until a favorable status. The exact implementation
calls the normal updater, but its completion callback reports `no_update` when
there is no pending update and receives no transport-success flag; retain that
limit instead of claiming an independently verified successful server response.
See the [pinned API schema](https://github.com/chromium/chromium/blob/fb096c0011f9d50f0a264a9376420cdea9c421e3/extensions/common/api/runtime.json#L430),
[implementation](https://github.com/chromium/chromium/blob/fb096c0011f9d50f0a264a9376420cdea9c421e3/extensions/browser/api/runtime/runtime_api.cc#L738),
and [updater delegate](https://github.com/chromium/chromium/blob/fb096c0011f9d50f0a264a9376420cdea9c421e3/chrome/browser/extensions/api/runtime/chrome_runtime_api_delegate.cc#L234).

A genuine update transition requires an older version already installed through
the normal Store, a real newer Store release, and observed newer installed
version followed by execution/restart checks. Current latest installs cannot
guarantee that condition. Keep `updateCheckCompleted` and
`versionTransitionVerified` separate. Reloading an unpacked fixture, changing
its manifest, faking a server, or calling reload cannot satisfy Store-update
proof. The ordinary toolbar Update path is separately source-backed at
`toolbar.ts:219` -> `service.ts:424` ->
`DeveloperPrivateAutoUpdateFunction::Run()` (foreground update check with
`install_immediately=true`); no direct private API invocation is planned.

## Remaining implementation/evidence gaps

- Reference run 41381085404 verified the full normal sequence through post-removal
  restart absence and final normal close on both platforms. Its original reports
  remain 19/20 because the old final predicate rejected any ID entry; the new
  bounded shape evidence proves that both remaining dictionaries are exactly
  empty. Execute the reviewed narrow registration-semantics correction once;
  do not retroactively relabel the historical reports as passed.
- Native helpers and full controller retain separate action/read-only contracts;
  see STORE-ACTION-CONTRACT.md. Reference success is not native-package success.
- Obtain genuine older-Store/newer-release conditions for version-transition
  proof, or report that particular gate unverified with completed check results.
- Run the complete test on actual built packages for both OS targets. Publish
  only bounded JSON, hashes/provenance, and explicit status; exclude profiles,
  full native trees, extension packages/source, logs, and account data.
