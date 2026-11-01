# Oracle evidence and remaining checks

This ledger separates exact packaged-source evidence, actual runtime
observations, and native-browser tests that still require a built binary. No
custom Chromium binary has been tested by this audit yet.

## Artifact identity and static REA evidence

| Item | Identity |
| --- | --- |
| Shipped extension | Always active Window - Always Visible 0.4.8, Web Store ID `ehllkhjndgnlokhomdlhgbineffifcbj` |
| CRX SHA-256 | `17e792706dcc8d7b1ad236bd090b662ca97786c085594b35da421851a33b655b` |
| Derived ZIP SHA-256 | `8eee6ad2b1fbc04726f77eb6eada38c700b91f13132cb64b8012cd9b7e7b038c` |
| REA extracted-tree identity | `1e756d9c930a703fe6cf74fe67f54ff3ad6491b3bf46a75ddaa851c7b7a7b7e4` |
| `main.js` SHA-256 | `8e0156ce545d5d6c7c724c2a134129c22619fc40ae306dcbc567cbd939ef1d13` |
| `isolated.js` SHA-256 | `b5147c3be4bb4911c7e2efbe47a13b055a54dbb3132057e9394ace94f564b51a` |

The CRX3 header was removed to produce the derived ZIP. The archive inventory
was complete (35 entries, 25 files, 10 directories, no integrity contradictions).
REA parsed six JavaScript files without parse failures. Its semantic graph was
partial with unknowns; direct packaged source and configuration were therefore
read for the audited behavior. None of the static evidence establishes that a
feature executed.

| Evidence | Scope |
| --- | --- |
| `ev_bae9e91a24ac07a8d6507799451d0888bad6e88f7a1dc5d27ebbfef248b17b95` | Archive inventory |
| `ev_35a6a6b40ae7644957100673bd4f6c950e22bf09df354ec56cbb11135041a3fc` | JavaScript application analysis |
| `ev_7da6d01a6df83d8236b8075eaac8ce02073780bf66cb561b7acd724a1afa0902` | Worker/module evidence |
| `ev_d617d3f71131444d78e989d27d7ec4391d657b92f9a5e59dad25646748606f8c` | MAIN-world injection evidence |
| `ev_36e7b0239c14de2d33b04628fa157d86527f0fdc10184883fccb11d522546776` | ISOLATED-world injection evidence |

The full initial bundle remains in the sibling investigation archive as
`rea-evidence-bundle.json`; its absolute machine path is intentionally not
published here.

## Controlled runtime environment

The audit acquired the official Chrome for Testing **156.0.8078.80 mac-arm64**
ZIP from Google's public Chrome-for-Testing storage. ZIP SHA-256:
`8bc590d1b1acac042a000234c768f31830f25a3983a83ed5e067114c87c4cad1`.
The executable SHA-256 was `c6279ef2230d17c6007ea1dc5342b67b0e6b0860741392de8eb0306aaeced292`
and matched the original ZIP member in a later check. CDP reported revision
`fb096c0011f9d50f0a264a9376420cdea9c421e3`. This is an unmodified test browser,
not this project's custom browser.

All runs used fresh owned profiles, a loopback fixture server, and an explicitly
selected local executable. The user's normal Chrome/profile was untouched. The
reference extension was loaded unpacked from the archived source. No debugging
focus emulation or lifecycle override is used by `tests/run.mjs`.

## Accepted GitHub-hosted macOS and Windows reference runs

[Reference run 41350893756, attempt 1](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41350893756/attempts/1)
ran source commit `8f9fbabdd29b889ed673fe29e771ba71d7b9fbff` on standard
GitHub-hosted `macos-26` and `windows-2025-vs2026` runners. On **both** platforms
the unmodified CFT baseline passed all **21 assertions**, and the exact shipped
extension passed all **28 oracle assertions**. The oracle explicitly verified
the inactive page's prototype-native `hidden=true` and `visibilityState=hidden`;
these are genuine background measurements, unlike the excluded local runs
below. The actual running revision matched
`fb096c0011f9d50f0a264a9376420cdea9c421e3` in all four runs.

| Platform | Mode | Passed checks | `results.json` SHA-256 |
| --- | --- | --- | --- |
| macOS arm64 | Baseline | 21/21 | `976b908c951118e050dde996c7145485e6a7ac99dc29bc8553d3b2ea75bba5b0` |
| macOS arm64 | Extension oracle | 28/28 | `ba736779e02ab7f0cef1ecde73d933666ded538877f0d971ceb53eacb9e700ce` |
| Windows x64 | Baseline | 21/21 | `b7f03193138a7e389d0dcf646ec65c1fe20d0f248df91f185792844b5959524e` |
| Windows x64 | Extension oracle | 28/28 | `e5cd11dff3863d64e0c84fa6d820f3024a8fe98aa03a048cc91e28db636fd2fa` |

The acquired Mac CFT ZIP matched the known digest above. The official immutable
Windows CFT ZIP measured
`16edb57d6107bf1c48a7c149b8d78b155fe614410093796dd72441fd6640540f`;
this digest is now pinned by the acquisition helper as well. Both downloads of
the extension matched the original CRX SHA-256 exactly. No compilation or
custom browser was involved.

The hosted measurements agree across both platforms:

- The native baseline reported hidden/hidden/not focused in the background and
  delivered normal visibility notifications. Its background rAF count was zero.
- With the extension enabled for all hosts, website instance getters reported
  visible/not hidden/focused while original prototype visibility getters still
  exposed hidden state. Same-origin, cross-origin, inherited about:blank frames,
  new background documents, and minimized-window checks passed.
- A new background rAF chain produced **3 callbacks in 1.3 seconds** in each
  oracle run. Timestamps and cancellation checks passed, but this is timer
  fallback activity, not a 60 fps guarantee.
- Ordinary hidden `location.href` redirects succeeded. A background script
  reload fetched the page again (request count **1 -> 2**) without a beforeunload
  dialog, despite the default redirect preference. Foreground script reloads
  and browser-initiated background reloads also succeeded.
- With fullscreen protection enabled, real fullscreen entry succeeded and
  initially returned `fixture-root`. Switching tabs left both native and
  spoofed element getters **null**, and the boolean aliases **false**. All four
  recorded entry/exit capture callbacks in each matching unmodified baseline
  occurred while the native document was still **visible and focused**; the page
  became hidden afterward. Calling
  `exitFullscreen()` then failed because the document was no longer active.
  The extension therefore did not preserve the claimed practical state on
  either platform.
- Late injection still allowed previously registered window blur and document
  visibility handlers to observe the real transition on both platforms.
- The ordinary MV3 fixture installed, executed content-script/worker/storage
  messaging, adopted version 1.0.1 on unpacked reload, preserved storage across
  browser restart, and stopped executing after removal in every run. This
  covers the fixture in CFT, not the future native binary or Web Store services.

The finite oracle pass tests the extension's **observed contract**, including
its limitations. It does not mean every marketing claim succeeded. Source
`main.js:78-96` also explains its document-capture visibility interception gap:
an ancestor window capture callback runs first (confirmed in the accepted local
trace). Source `main.js:48-76` explains why its reload-only beforeunload attempt
does not supply a general redirect blocker, and `main.js:215-220` can overwrite
its fullscreen snapshot with null before suppression. These gaps motivate
deliberate native improvements, which still need custom-binary verification.

Attempt 1's measurement steps succeeded; its separate draft-release publisher
failed with HTTP 403. [Attempt 2](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41350893756/attempts/2)
repeated **21/21 baseline and 28/28 oracle checks on both platforms**, again with
native-hidden validation and animation counts zero/three, respectively. Its
four report hashes were:

| Platform | Mode | Attempt-2 `results.json` SHA-256 |
| --- | --- | --- |
| macOS arm64 | Baseline | `739837a91d7137b44e8b643c7e4c3bf37debb351860593119f00494801570877` |
| macOS arm64 | Extension oracle | `422d8b11bb6b7240e2100231baf1acc716022ec2f0642c03561dc4a35f55fd72` |
| Windows x64 | Baseline | `ef0208d1bfac14d3b1c2419f7247cf090d20a62ecb07bc5a26bffa6812a51784` |
| Windows x64 | Extension oracle | `2be0c762816d2af32d99392abccdec99ec74010067bb148f94de70ed13d74634` |

The attempt-2 publisher also failed with HTTP 403 on both platforms. Publication
status is separate from measurement status; all hashes above are read from the
accepted job logs, not assumed uploaded assets. Neither attempt is a successful
browser build or a successful evidence-release publication.

## Earlier accepted local observations

`extension-1/results.json` under ignored `.runtime/oracle/` has SHA-256
`8386fd327ad085338d2a7e8bd4e9543eced8e9c03382899025918a7bdb0b1811`.
This direct CDP-controlled run verified a genuinely hidden document by calling
the original prototype getters: native hidden was true/native visibility was
hidden while the instance getters reported false/visible and focus true.
Same-origin, cross-origin, and about:blank frames reported protected state.
The run also recorded:

- Visibility events reached a website window capture listener even though the
  extension blocked document listeners.
- A hidden-started animation chain produced three callbacks in 1.3 seconds;
  its native timer fallback remained throttled.
- An ordinary hidden `location.href` redirect succeeded.
- Fullscreen protection enabled: real entry succeeded, switching tabs exited
  fullscreen, and both spoofed/native element getters returned null. Fullscreen
  events were delivered. It did not preserve the claimed practical state.
- Disabling the `hidden`/`visibilityState` preferences did not restore those
  getters.
- Late attachment changed getters but pre-existing blur/visibility handlers
  still ran.

This early harness run was **not an overall pass**: an initially overbroad
event assertion incorrectly expected the extension to block ancestor capture
listeners, and unpacked MV3 reload required enabling developer mode. Those
harness assumptions were fixed. The individual raw measurements above remain
valid evidence; they are not a claim that the full test suite passed.

The accepted baseline REA process capture is
`ev_b25e6e2c9b58143ec286b51201e98982785dfe9b353349a8fc0e4489857546aa`.
It ran the real test executable/controller against the unmodified browser,
exited 0, and passed all **17 then-current assertions**, including unpacked MV3
installation, worker messaging/storage, version-changing reload, restart
persistence, and removal. Its report `baseline-rea2/results.json` SHA-256 is
`272fe80230bd36d8b341c3f189d8cda8738aad83a0c4597c4d4b23eb98b4984f`.
Later harness additions (window identity, cancellation, optional assertions)
are not included in that historical 17-check pass.

The local baseline measured fullscreen exit callbacks while the native document
was still **visible and focused**, before the eventual hidden state. A
renderer-only hidden snapshot could not guarantee retention for that ordering.
The native design was subsequently expanded to hide an eligible deactivated tab
before its real fullscreen exit, without retaining OS/CSS fullscreen. The
current optional harness therefore requires natural tab-switch snapshot
retention after confirmed real entry; it no longer accepts this main scenario
as `not-covered`. It also verifies normal foreground clearing, no resurrection
on later hide, and explicit visible exit. None of this is a custom-binary pass
until the built browser executes those assertions.

REA process-capture limits apply: sampled process trees can miss short-lived
children, filesystem observations are before/after snapshots, inherited ambient
environment is not recorded, and executable hashing is a prelaunch sample,
not atomic OS image binding. These are controlled integration results, not a
formal proof of browser equivalence.

## Excluded runs and unresolved runtime anomaly

Later reference runs (`extension-rea` and `extension-3`) reported native
prototype visibility as visible even for an inactive tab in the same window.
Their fast animation counts and absent visibility transitions cannot establish
hidden-page behavior. The harness now explicitly fails such an oracle run.
`extension-rea` had superficially passed its previous 23 assertions, but that
pass is **excluded** from background-equivalence claims. Its REA ID is
`ev_971adfbff3db7ee3ba28c37b754ca823f20dc0d2e848d9e167b77cf588893c4f`
and report SHA-256 is `f9e8a70752b04fc4618f8b14dc7e3e88e361f855329bfcded15650cfad4e14ee`.

Diagnostics confirmed that both controlled tabs had the same native window ID,
the cover tab was active, the main tab inactive, and an isolated-world native
getter also returned visible. Explicitly turning off focus emulation in a
separate diagnostic did not change it. The CFT executable still matched its
ZIP. No cause is established. This observation remains unresolved rather than
being used to inflate the extension's capability or callback rate. A later
unmodified **baseline** run also showed the anomaly (native hidden=false in an
inactive tab and 79 animation callbacks/1.3 s), so it is not specific to the
extension. That 20-check run intentionally failed its background expectations;
its report `baseline-final/results.json` SHA-256 is
`b2465f4dd30c021cc1a92ac55b7f37358cf6f8b1bc5b6966e853296af8b63e42`.
The genuinely hidden earlier baseline remains the accepted observation.

`tests/acquire-reference.py` enables independent hosted reference runs without
checking out Chromium. It downloads the version-pinned CFT package and current
CRX, rejects a changed CRX/derived ZIP, safely extracts both, and emits the
browser/extension paths plus `reference-provenance.json`. Local end-to-end Mac
acquisition/extraction reused the verified official ZIP and freshly fetched the
exact original CRX successfully. Seven finite archive-boundary tests passed.
The initial Windows acquisition recorded its hash from the official immutable
version URL; that measured digest is now pinned for future acquisitions too.
The running browser's revision is independently checked by the harness.
The extraction implementation preserves bounded Mac framework symlinks and
rejects traversal, symlink escape, duplicate paths, and extraction-budget
overflow. No extension package/source should be uploaded as public evidence.

The runtime REA session was exported to ignored
`.runtime/oracle/rea-runtime-evidence.json` (6 records, 507199 bytes, SHA-256
`4e78938958936175b8fb95563bab80c9b808a0a112148e359845f3bf05ad4f95`).
It contains machine/process metadata and is not intended as a public release
artifact. Public CI should upload only the finite `results.json` and
`browser.log` outputs described in [tests/README.md](../tests/README.md).

## Required before a completed-browser claim

The subsequent hosted run
[41351983527](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41351983527)
completed measurement and draft publication successfully on both platforms.
Root downloaded all finite assets and verified all six SHA-256 entries per
platform (two reports, two browser logs, acquisition provenance and status).
The accepted report digests are:

| Platform/mode | Assertions passed | Report SHA-256 |
| --- | --- | --- |
| macOS baseline | 21 | `7b4ae049a9e05c34122641a7abaab265f05f336d55b23fcc7ed842e44226e5d1` |
| macOS shipped extension | 28 | `32312aac593c1642ae9ce076ee401c1cd81dc7667aaa08b6618914ab0ac75729` |
| Windows baseline | 21 | `d722a64dac3a0e770d258fc6b476020c69e1880849f9f67eb6d0e5bf6661b44e` |
| Windows shipped extension | 28 | `4df5910f97ccd9537159480bef27ced5184082513f7487bd1c8f906ec8cb1a46` |

Both baselines reported true native hidden state in the background; both oracle
runs reported spoofed instance getters alongside true native hidden prototype
getters. The local visibility anomaly does not contaminate these clean-host
results. This establishes the reference behavior and unpacked MV3 fixture
coverage; the custom native browser and Chrome Web Store service checks remain
pending.

- Run the default native tests on actual built macOS arm64 and Windows x64
  packages, plus a master-feature-disabled baseline on the same binaries.
- Run strict optional fullscreen/reload tests. Both hosted reference platforms
  exit fullscreen while visible before becoming hidden; the native improvement
  must demonstrate its new eligible tab-deactivation ordering. After real
  entry, the same-window natural switch must retain the binding snapshot while
  bounded polling confirms CSS `:fullscreen` is false and the OS window exits
  fullscreen. Clear entry events before checking exit suppression. Returning
  foreground and a later re-hide must not resurrect stale state; visible
  Escape/exit must stay normal. A deterministic Blink C++ fixture can supplement
  this by setting actual page visibility hidden before native exit, but cannot
  replace the required natural browser scenario. Synthetic-event tests alone
  do not cover a native fullscreen exit.
- The strict fullscreen scenario establishes an input before entry and checks
  real CSS `:focus`, active element, value, and selection before deactivation
  and after return. It uses `Target.activateTarget` for tab switches, avoiding
  `Page.bringToFront`'s extra contents-focus call that could conceal broken
  saved-focus restoration. No `.focus()` is called after initial setup and
  before the restoration assertion. Background actual focus must be false;
  the spoofed document-focus binding is not evidence for this check.
- The optional native case also queues a real cover/original target activation
  pair after another actual fullscreen entry. It must settle within bounded
  polling to exited CSS/OS fullscreen, cleared foreground bindings, preserved
  input focus/value/selection, and no snapshot resurrection on a later hide.
  This is supported queued activation, not synthetic C++ observer reentrancy.
  It still requires execution against the compiled custom browser; no local
  reference result is a pass for this new native behavior.
- Re-run the now-validated macOS/Windows reference suite when the pinned browser
  or extension artifact changes. A changed extension digest requires a new
  audit, not silently using a new oracle.
- Verify normal browser UI visually, standard Chrome Web Store installation,
  and supported extension store-update/removal behavior on both platforms.
  The unpacked MV3 fixture is not a store-service test.
- Keep freeze/discard/sleep, indefinite scheduling, every third-party extension,
  and Google-restricted services outside the tested claims unless separately
  verified.

## Detached-document constructor regression

After the hosted 21/28-check runs, review found a native animation-controller
constructor path that could dereference a missing window for detached documents,
even with the feature disabled. The browser harness now tests eight detached or
inert owner documents and fourteen DOM operations before its background tests:
`createHTMLDocument`, DOMParser HTML/XML, `createDocument`, live/detached document
clones, cross-document imports, and template-content owner documents, including
nested templates, fragment/template cloning, and imports. A second evaluation
checks that the renderer still responds. Every harness mode includes these
regressions; native/baseline mode asserts ordinary detached focus state too.

The new regression subsets passed in isolated original-CFT local runs:

| Run | Regression checks | Full report SHA-256 |
| --- | --- | --- |
| `detached-baseline` | 5/5 | `808bbdcf2abae0434ce5e364c2866d87a07c8b66e72191248c04115bfdcc68ed` |
| `detached-oracle` | 4/4 | `533e279fa08e938cc6da43f4c491b28cee4e860ff179b9b4302477d677ab1f41` |

All documents had null `defaultView`, hidden visibility, and no own hidden
getter. The unmodified browser returned focus false for all eight. The
extension returned focus **true** for all eight because its realm-wide Proxy
does not check the receiver's eligibility. Native behavior deliberately keeps
these documents outside focus spoofing. Both full local runs still failed the
known unrelated background-visibility anomaly; the regression subset is not an
overall background-suite pass. These additions were not included in the earlier
hosted 21/28 counts and still require execution against the custom native build,
including its master-feature-disabled configuration.

The focus-sentinel mechanics were also observed in a later unmodified local CFT
run: `activeElement='input'`, CSS `:focus=true`, value `fullscreen focus sentinel`,
and selection `[2,7]` before deactivation; CSS focus became false in the inactive
tab, then returned true with the same input/value/selection after target
activation alone. The whole local run remained failed for the known background
visibility anomaly, and real fullscreen was not held at the pre-switch sample.
This validates the probe mechanics, not the new native fullscreen scenario.
Its report `fullscreen-focus-baseline/results.json` SHA-256 is
`7e7c892d634d00151beb47c9020a72448cb6ee274abc11854cef9209208bdf5c`.

## Normal launch with no debugging connection

`tests/no-debug.mjs` and its owned HTTP fixture close a separate verification
gap: the browser is launched normally with a fresh profile and two website
URLs, without CDP, WebDriver, remote-debugging/automation flags, extensions, or
focus/lifecycle emulation. Website inline JavaScript only reads visibility/focus
aliases and version metadata and posts observations; it does not override APIs
or select tabs. The paired test requires the same executable to demonstrate
stable genuine hidden state with `AlwaysActive` disabled, then stable visible
and focused state for both websites with default settings. It does not assume
which startup tab is selected. Samples must be later than the settling period
both in controller time and website elapsed time, and remain stable for the
declared observation span.

The current control implementation passed **7/7** checks on the unmodified local
CFT browser with no debugging connection. It observed genuinely hidden,
unfocused website reports, `navigator.webdriver=false`, the exact expected full
browser version, no `DevToolsActivePort`, and only normal launch flags. PID,
profile, creation identity, and the owned POSIX process group were verified
before cleanup; the root and process group were gone afterward. Report
`.runtime/no-debug-reference-control-final/results.json` SHA-256:
`4cabcad193e36304307fde284835f685012d27ade475d48a3276bedce5d89257`.

Negative controls also behaved correctly: unmodified CFT **failed** the native
visibility/focus requirement. A paired CFT run passed all seven control checks
and failed that native requirement while passing its other six checks. Its
report `.runtime/no-debug-reference-paired/results.json` SHA-256 is
`6744d30f40b45e546bd7cc02b733ffea124b0c412ac82b3853a2b77cec71e235`.
That negative run preceded the stricter website-elapsed settling filter; the
new filter cannot turn its incorrect native state into a pass.

These observations validate the connection-free test mechanics, not a native
browser implementation. The native paired run remains required on actual built
macOS and Windows packages. Publish only its finite `results.json`, excluding
profiles and browser logs. Source revision is recorded as an expectation, not
claimed observable from website metadata; exact build provenance remains a
separate requirement. The successful normal-launch control also does not resolve
the earlier local debugging-session visibility anomaly.

A final interruption smoke sent SIGTERM to the controller at six seconds. It
recorded the interruption, verified and terminated only its owned browser
PID/group, wrote a failed/incomplete report, and exited at 6.401 seconds; both
root and process group were gone. The report SHA-256 is
`3f84a36f49e6c8d4b6b968adb6d18bb96f3639d5a60c378b9ca611cc4068e7d1`.
Cleanup has an 18-second absolute budget with smaller command timeouts and
refuses unverifiable ownership. The local cleanup evidence is macOS-only;
Windows CIM/PID-tree handling still needs its hosted execution.

## Read-only actual Store listing preflight

`tests/store.mjs` uses a separate fresh owned browser profile and minimal CDP
controller flags. It navigates to the original public extension listing,
collects document HTTP status and bounded DOM/AX Add-button state, and reads
only capability **types**. It does not call installation methods, click Add,
accept a permission dialog, load an extension, or alter security/policies.
Launch/setup, listing wait, final capture, and cleanup are bounded separately.
Only finite `results.json` summaries are publishable.

The initial local capture passed **6/6 capture checks** (report SHA-256
`a85b5ee4fdbe92170f40d1e2e8d6a67f662540c1c7739746eb2e77b46e83bee4`).
A later settled capture with the compiled read-only native UI helper again
passed **6/6**, report SHA-256
`a5a83672db8257242078d2e68035f1d024d9ec2edbf91794143bd7eaf33d26cd`.
Both are CFT reference observations, not native-browser compatibility results:

- The actual audited listing loaded with HTTP **200** and the expected title.
- DOM and AX both showed **Add to Chrome disabled**; DOM reported it visible,
  `disabled=true`, and `pointer-events:none`.
- The page displayed “Switch to Chrome?” and an AX button named “Switch to
  Chrome to install extensions and themes Install Chrome”. The reason for this
  frontend state has not yet been established by these captures.
- `webstorePrivate` had type `object`, while `beginInstallWithManifest3` and
  `completeInstall` had type `function`. Neither method was invoked. API
  exposure alone does not establish normal Store install readiness.
- The port-zero CDP launch reported `navigator.webdriver=true`. Separately,
  the normal-launch CFT sample had no Google Chrome UA-CH brand. These are
  observations, not proof of the disabled button's predicate.
- The native helper verified the owned PID/profile and reported AX trusted and
  available. Its bounded/truncated traversal used an `AXApplication` fallback
  rather than an observed `AXWindow`, so it does not prove that a permission
  dialog target is available. No native UI action was performed.
- The owned browser closed cleanly; root and POSIX process group were gone.

The installation and permission-dialog gate remains **not tested**, and the
disabled Add button is an unresolved readiness blocker. A preflight capture
pass must not be presented as a successful extension installation or as proof
that the future native browser supports the normal Store UI. Shipped frontend
predicate analysis and actual built-browser interaction are separate follow-ups.

The helper was subsequently tightened: application access and observed roots
are recorded separately from actual native windows. `ready` now requires an
owned `AXWindow`, known non-hidden application state, and known non-minimized
window state. An application-only tree or unknown visibility cannot establish
native-dialog readiness. The older capture above predates this stricter check;
the next hosted preflight must exercise the updated helper.
