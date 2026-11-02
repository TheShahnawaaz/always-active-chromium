# Browser behavior tests

Requires Node.js 22+ (native `WebSocket`), a **headful** macOS/Windows desktop,
and a browser executable. There are no npm dependencies. The controller creates
a fresh profile under the selected output directory and a loopback fixture
server. It never opens the user's regular Chrome profile. Choose a new output
directory for each run; the harness refuses to reuse a profile.

```sh
node tests/run.mjs --browser /path/to/chromium --mode native --output reports/native
node tests/run.mjs --browser /path/to/chromium --mode baseline --disable-features AlwaysActive --output reports/feature-off
node tests/run.mjs --browser /path/to/chromium --mode native --features AlwaysActiveFullscreen,AlwaysActiveBlockBackgroundReload --output reports/optional
```

`baseline` expects ordinary Chromium semantics. Use an unmodified browser, or
disable the native master feature explicitly as shown. `native` expects the
default native feature. Tests fail with a nonzero exit status; `results.json`
records individual assertions, observations, and coverage limitations.

To compare the actual shipped extension, use a browser that permits unpacked
loading (Chrome for Testing or Chromium; branded Chrome can reject the switch):

```sh
node tests/run.mjs --browser /path/to/chrome-for-testing --mode oracle --extension /path/to/exact-unpacked-extension --output reports/oracle
```

The oracle enables the extension on all hosts in its own profile and closes its
owned onboarding popup before making controlled tabs. It asserts that a native
prototype getter really reports hidden so that an accidentally visible or
emulated page cannot be accepted as background evidence. Its expected event
behavior deliberately differs from native mode: version 0.4.8 leaks visibility
events to window capture listeners. An independent native implementation can
close that gap.

`python tests/acquire-reference.py --platform mac-arm64 --output /fresh/reference`
downloads official pinned CFT 156.0.8078.80 and the current store CRX. On Windows
use `--platform win64`. It requires the exact audited CRX SHA-256 and the known
Mac/Windows ZIP digests, preserves Mac framework symlinks during safe extraction, and
writes `reference-provenance.json`. In Actions it emits `browser`, `extension`,
`provenance`, `cft_sha256`, `extension_sha256`, `version`, and `revision` through
`GITHUB_OUTPUT`. The browser test independently asserts the actual running
revision. The acquisition directory must be new; don't upload its packages or
extension source. A changed extension digest requires a new audit, never an
automatic acceptance.

Coverage includes document-start reads, tab changes, newly created background
tabs, same-origin/cross-origin/about:blank frames, minimized windows, getters,
focus, native and synthetic event paths, ordinary input focus transfers,
animation callbacks started in the background, location redirects, and reload
policy. CDP only controls the tests; no focus emulation or lifecycle overrides
are part of the harness or the shipped browser.

Every mode also constructs detached HTML/XML documents through
`createHTMLDocument`, `DOMParser`, `createDocument`, and `Document.cloneNode`,
then performs cross-document imports. It creates inert template owner
documents through `HTMLTemplateElement.content`, including nested templates,
fragment/template clones, and imports. These cases must complete without a
renderer crash even with the master feature disabled. Detached documents retain
null `defaultView` and normal hidden visibility; native/baseline mode also
requires normal false document focus. Oracle focus is observed separately
because its realm-wide `Document.prototype.hasFocus` Proxy can affect detached
receivers too. A second CDP evaluation verifies the renderer still responds.

The optional reload test checks that hidden renderer script reloads are
cancelled when the feature is selected while foreground script reloads,
browser-initiated reloads, and ordinary redirects still work. Optional native
fullscreen tests require successful real API entry and snapshot retention after
a natural same-window tab switch. Entry notifications are cleared first; the
controller then polls up to five seconds for native CSS `:fullscreen` to clear
and the OS window to return to normal before checking getters and exit events.
Only the website bindings may retain the original element/true booleans. The
foreground return must clear that snapshot, a later hide must not resurrect it,
and an explicit foreground exit must work normally. Failure to enter fullscreen
or retain the snapshot is a failed optional-native assertion, not uncovered
success. Default and master-disabled configurations must preserve normal exit
state. Reference/oracle runs record their observed fullscreen defect without
claiming they satisfy this native improvement.

The fullscreen scenario establishes an input focus sentinel before entry and
records its value/selection, `activeElement`, and native CSS `:focus`. Tab switches
use `Target.activateTarget`; `Page.bringToFront` would explicitly focus contents
and could hide a saved-focus regression. After return, the native optional test
requires the same input, real `:focus`, value, and selection without calling
`.focus()` again. A background input must lack real `:focus`. The spoofed
`document.hasFocus()` binding is not used as evidence of actual input focus.
After another real fullscreen entry, the native optional case also activates
the cover tab and immediately the original tab, queuing ordered CDP requests
before awaiting their acknowledgements. Bounded polling must confirm actual
fullscreen exit, cleared foreground bindings, and restored input focus/value/selection. A subsequent
hide must not resurrect a snapshot. This is an ordinary queued A-to-B-to-A
activation regression, without synthetic C++ reentrancy or refocusing calls.

The representative MV3 fixture uses a content script, asynchronous service worker
messaging, and `chrome.storage.local`. The harness enables developer mode through
the browser's own extension UI API in the test profile, loads it through CDP's
`Extensions.loadUnpacked`, edits version 1.0.0 to 1.0.1 and reloads it, checks
storage across browser restart, and uninstalls it. This establishes **unpacked
fixture compatibility**, not Chrome Web Store installation or automatic store
updates. Store installation/update remains a separate release check on both
platforms.

Upload only `results.json` and `browser.log` from each run. Do not upload the
generated `profile/` or `mv3-fixture/` directories. The fixtures contain no user
data, but profiles are not suitable release artifacts. UI chrome pixels,
extension-store services, enterprise policies, indefinite background execution,
discard/freeze/sleep behavior, and broad third-party extension compatibility
remain outside these finite checks.

## Normal launch without a debugging connection

```sh
node tests/no-debug.mjs --browser /path/to/chromium --output reports/no-debug
```

This separate dependency-free controller uses **no CDP, WebDriver, automation
flags, extension, focus emulation, or injected browser-control script**. It
launches the normal executable with a fresh owned profile and two loopback URLs.
Each website's inline script only reads visibility/focus aliases and version
metadata, then posts observations to its own HTTP server. The controller neither
selects tabs nor changes focus. It accepts whichever control website actually
becomes hidden; startup URL order is not assumed.

The default `paired` mode first runs the same executable with
`--disable-features=AlwaysActive` and requires stable later reports from a
genuinely hidden/unfocused page. It then launches a separate default profile and
requires **both** pages to stably report visible/focused state. Both phases must
pass. Each phase has a 45-second deadline, a five-second settling period measured
both after launch and within each website, and a 2.5-second stable observation span; successful pairs normally finish much
sooner. `--timeout-ms`, `--settle-ms`, and `--stable-ms` can bound experiments.

For unmodified CFT, `--mode control` validates the passive mechanics. Its
`--mode native` check must fail; a reference browser is not accepted as a native
implementation. A native-only result does not replace the paired control.
The fixture reports `navigator.webdriver=false`; the controller also verifies
the absence of `DevToolsActivePort` in the owned profile. Website UA-CH full
version metadata is checked against the expected pin, while an exact source
revision is explicitly outside this connection-free observation.

Cleanup checks the exact spawned PID's executable/profile/start identity before
signalling. POSIX uses a new verified owned process group; Windows verifies the
owned process through CIM before terminating its exact PID/tree. It does not
quit applications by name or signal unrelated browser processes. Interruptions
request cleanup and an incomplete run fails. Cleanup has an 18-second deadline;
individual identity queries and Windows tree termination have smaller bounded
timeouts. Unverifiable ownership or incomplete cleanup fails the run.

Publish **only** the no-debug `results.json`. Exclude its `profile-control/`,
`profile-native/`, and `*-browser.log` files. The JSON retains bounded samples,
precise launch arguments, version expectations, ownership/cleanup evidence,
and the finite test's limits.

## Read-only Chrome Web Store preflight

```sh
node tests/store.mjs --browser /path/to/browser --output reports/store
```

This opens the actual audited extension listing in a fresh owned browser profile
and captures its document HTTP status, finite DOM/AX button labels and enabled
states, actual browser revision, and `typeof` results for `webstorePrivate` and
its installation methods. It does **not** invoke those methods, click Add,
accept a permission dialog, install/load an extension, or change security and
policies. Its independent minimal launcher uses only fresh-profile/first-run
flags and loopback remote debugging for the read-only test controller; it does
not use the ordinary extension fixture launcher's unsafe-debugging or network
suppression flags. The listing wait defaults to 60 seconds, bounded by
`--timeout-ms` (5-120 seconds), and button state must settle before capture.
Launch/setup, final capture, and cleanup have separate absolute wall-clock
bounds; an interrupted early launch still requires owned identity verification
before any fallback signal.

An optional `AA_STORE_UI_HELPER` supplies owned-PID native UI prerequisites:
the compiled `tests/ui/store-ui.swift` helper on macOS or the exact
`tests/ui/store-ui.ps1` path on Windows. The controller imposes a 15-second
deadline and 64 KiB output bound. Its `ready`, `untrusted`, `unsupported`, or
`error` status is recorded separately; exit zero alone is not readiness. Missing
helpers are reported as unsupported, and no accessibility permission is granted
or native UI action performed automatically.
On macOS, application accessibility is distinct from native-window readiness:
only an owned `AXWindow` with known non-hidden/non-minimized state can report
`ready`. Application-only trees and unknown visibility remain unsupported.

A passed **capture preflight** is not a completed Store installation or native
extension-compatibility test. An Add button can be observed while disabled;
readiness fields retain its enabled state, capability types, and native UI
status. Real Add/permission-dialog interactions, restart, genuine Store update,
and removal remain later explicit verification gates against built browsers.
Publish only `results.json`, excluding `profile/`, `browser.log`, full DOM, and
full accessibility trees. Cleanup closes only the verified owned browser, with
PID/profile/creation-identity-checked fallback signals if needed.

## Normal Store permission-dialog inspection

```sh
node tests/store-dialog.mjs --browser /path/to/browser --output reports/store-dialog
node tests/store-dialog.mjs --browser /path/to/browser --output reports/store-dialog-ubol --target ubol
```

This separate stage defaults to the original audited Always Active listing.
`--target ubol` selects the audited uBlock Origin Lite listing; these are the
only two allowed targets. The read-only `store.mjs` preflight and hosted workflow
accept the same selection, and published status must match the report's target.
Audited version/CRX fields describe the static reference, not a verified live
Store version or installation. No target is installed by this inspection.

Each target uses a fresh minimal browser profile. The normal browser window is requested at 1280 by 900 pixels
so the Store's desktop layout fits; no viewport/device emulation is used.
Actual viewport dimensions and button rectangles are retained for diagnostics.
If an enabled Add button is clipped or obscured, one bounded ordinary target
scroll is attempted with `DOM.scrollIntoViewIfNeeded` on that observed element.
Document scroll position/extents and fresh button geometry are recorded. Every
enabled/visible/viewport/hit-test gate must still pass afterward; scrolling never
forces the button or substitutes coordinates for a failed gate.
It requires an enabled, visible, unobscured Add button and
strict owned-PID native UI prerequisites before dispatching normal CDP mouse
move/press/release input to that button. It never calls `element.click` or an
installation API. The native helper runs in read-only `dialog` mode afterward;
there is **no acceptance action**.

The captured prompt must belong to a verified same-PID native window and contain
the exact selected-target native Add heading, enabled Add extension/Cancel button
roles and labels, and substantive permission text captured from that same owned
prompt. No uBOL permission phrase is guessed or copied from the original target.
Focused ancestry and a macOS owned
visible window/sheet subtree are recorded as distinct proof kinds; the latter
must establish its owning window and known visible/non-minimized state without
claiming a focused-element ancestor chain. Only records carrying the relevant
ownership proof contribute prompt text or buttons. Actual role/subrole/title/value
fields are retained as finite observations; helper exit zero or a generic
browser window alone does not establish prompt identity. Four probes are
scheduled around 0.5, 10, 20, and 30 seconds after Add, within a 45-second total
dialog budget and a 15-second maximum per probe, so fast empty observations do
not exhaust the attempt count immediately. The controller then closes the owned browser
normally, cancelling the unaccepted prompt. Read-only target-registry queries
are attempted, and persisted extension preferences must contain no target entry
after closure. Forced fallback cleanup is recorded and cannot pass the normal
close/cancel check.

Set `AA_STORE_UI_HELPER` to the compiled macOS helper or exact Windows script as
for preflight. Main actions have a three-minute budget and cleanup has an
additional 18-second budget, with smaller listing/dialog/probe deadlines. Publish only `results.json`; exclude the
profile and browser log. This is a dialog-inspection gate, not a successful
installation, restart/update/removal test, or native-binary compatibility claim.
Local CFT's disabled Add state is not used to attempt an Add click; initial real
modal capture is intended for the hosted environments where readiness passed.

## Full normal Store compatibility controller

```sh
node --test tests/test-store-compat.mjs
node tests/store-compat.mjs --browser /path/to/browser --output reports/store-compat
```

The controller has a fixed uBlock Origin Lite target and is separate from the
read-only inspection entrypoints. It requires jointly reviewed
`AA_STORE_UI_HELPER` and `AA_STORE_ACTION_HELPER` paths. A missing action helper
fails before any browser or profile is created. The reviewed reference sequence
passed **20/20 phases on both platforms** in run `41384092270`, controller
commit `43c9cd2`; see the [verified evidence](../docs/oracle-evidence.md#completed-normal-store-reference-sequence).
Offline tests remain boundary checks, and CFT reference success is not a
custom native-browser result. Further reference runs require a new issue.

The controller uses the real Store Add button, verifies the captured native
target heading and actual permission text, and delegates acceptance to the
separate native action helper. After normal shutdown it requires the installed
audited version, semantic manifest digest, matching inserted public key if
present, and exact digests for four selected shipped JavaScript files. Raw
manifest digest is recorded; formatting/key insertion may change it. No other
semantic manifest change is accepted.

It restarts only its created profile, reads the actual own-origin worker's
`getEnabledRulesets` response, repeats that probe after another normal restart,
and makes one ordinary own-extension update request. It then uses the visible
Remove button on the selected real `chrome://extensions` item and a separate
native confirmation. Removal must survive restart and normal close, with verified
persisted **registration** absence. `targetRegistrationAbsent` accepts only no
target ID entry or an actually empty JSON dictionary with complete untruncated
evidence and no parse/container uncertainty. Every nonempty, pending, malformed,
oversized or unknown entry still fails. `targetAbsent` separately retains the
physical ID-entry result: it stays false when an empty identifier dictionary
remains. No claim of removing every identifier or preference byte is made.
The final phase is `persistedRegistrationAbsent`; the removal result is
`persistedRegistrationAbsenceVerified`, and combined coverage is
`normalRemovalWithPersistedRegistrationAbsence`. The native removal receipt,
live registry absence, post-removal restart absence and normal final close all
remain mandatory alongside the static preference check. The ordinary update result and
`versionTransitionVerified` are separate: `no_update` does not prove an upgrade
or independently establish successful server transport.

The action helper has an outer hard 15-second process deadline. Each action is
invoked once. Timeouts, transport errors, incomplete receipts, or ambiguous
action results are marked uncertain and never retried; acceptance/confirmation
becomes `null`. Only a complete matching receipt explicitly reporting no attempt
and no action can establish that no native action occurred. A bounded read-only
registry query is attempted after an uncertain result, and final persisted state
is retained when owned shutdown and remaining cleanup time permit.

Every install/removal prompt probe also retains a diagnostic native trace under
`observations.promptCaptures`, including failed attempts. At most four traces
per operation are retained, each capped at 32 KiB with conservative nested JSON
accounting. Native root titles, heading roles, focus ancestry, owning-window
proof, and relevant button/checkbox records are preserved; source indexes and
explicit truncation metadata describe omitted controls. These traces omit
profile/executable paths and are diagnostic projections. The original probe
continues to supply the unchanged permission/action gates.

Main work has a 12-minute budget, plus at most 18 seconds for final cleanup.
Publish only the bounded `results.json`; exclude owned profiles, all restart
logs, extension source/package files, and full native trees. The report's
coverage fields preserve unverified genuine-version-transition evidence even
if installation/execution/restart/update-check/removal phases pass. See the
[phase plan](STORE-COMPATIBILITY-PLAN.md) and
[native action contract](STORE-ACTION-CONTRACT.md).
