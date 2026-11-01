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

Coverage includes document-start reads, tab changes, newly created background
tabs, same-origin/cross-origin/about:blank frames, minimized windows, getters,
focus, native and synthetic event paths, ordinary input focus transfers,
animation callbacks started in the background, location redirects, and reload
policy. CDP only controls the tests; no focus emulation or lifecycle overrides
are part of the harness or the shipped browser.

The optional reload test checks that hidden renderer script reloads are
cancelled when the feature is selected while foreground script reloads,
browser-initiated reloads, and ordinary redirects still work. Optional fullscreen
tests assert hidden event filtering, boolean aliases, and explicit foreground
exit. Snapshot retention is asserted when observable; a native exit that happens
while visible before the hidden transition is recorded as `not-covered`, never
as a snapshot pass. That ordering occurs on the measured macOS baseline.

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
