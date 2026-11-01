# Extension behavior audit: version 0.4.8

The reference is the actual Chrome Web Store CRX for `ehllkhjndgnlokhomdlhgbineffifcbj`,
not a recreation based on its description. Its SHA-256 is
`17e792706dcc8d7b1ad236bd090b662ca97786c085594b35da421851a33b655b`.
The CRX and extracted source were archived outside this repository. Static REA
analysis and controlled macOS browser runs are indexed in
[oracle-evidence.md](oracle-evidence.md). Source locations below refer to that
exact extracted artifact, not this repository's native patch.

The extension changes what website JavaScript sees. It does not actually focus
every tab, move keyboard input to hidden pages, prevent OS sleep, keep a real
fullscreen window, or guarantee that a website cannot detect a tab change.

| Surface | Actual implementation/default | Evidence and limits |
| --- | --- | --- |
| Activation | Global `enabled=true`, but `hosts=[]`; no website is protected on a fresh install until a hostname or `*` is selected. | `worker.js:136-177`; fresh runtime storage was empty and these are fallback defaults. The native project's all-site default is a requested design change. |
| Injection | Registered `document_start` scripts, MAIN and ISOLATED worlds, all frames, origin fallback for related opaque/about frames. Host matches determine coverage. | `worker.js:144-175`; same-origin, cross-origin, and inherited about:blank probes worked when all hosts were selected. Browser/extension privileged pages are not ordinary host matches. |
| Visibility getters | Own non-configurable `document.hidden=false`, `webkitHidden=false`, `visibilityState='visible'`, and `webkitVisibilityState='visible'` while enabled. | `main.js:21-37,110-126`; background runtime confirmed the spoof. Calling the original getter from `Document.prototype` bypassed it. The separate `hidden`/`visibilityState` options are saved but never consumed by injection code. |
| Focus getter | A Proxy around `Document.prototype.hasFocus` returns true when enabled and focus blocking is allowed. | `main.js:128-136`; hidden top/frame probes returned true. The Proxy also returned true for eight detached/inert documents created in the protected realm, even with null `defaultView`. Actual OS/keyboard focus stays elsewhere. A previously cached function can bypass a late-installed Proxy. |
| Visibility/page-hide events | Stops `visibilitychange`, `webkitvisibilitychange` at document capture and `pagehide` at window capture; one initial visibility event is allowed if injection began while truly hidden. | `main.js:39-46,78-101`. A website's window capture listener receives document visibility events before the extension's document listener. This leak was observed even with document-start injection. |
| Focus/blur events | Suppresses document/window blur; permits one document/window focus event and suppresses later ones. Element focus/blur is allowed. | `main.js:138-161`; synthetic event probes and real input focus transfers preserved element behavior. Late attachment leaves earlier registered listeners able to run first. |
| Mouse events | Suppresses mouseleave only when its target is document/window; suppresses mouseout only when its target is `html`/`body`. | `main.js:163-177`; child-element mouse events pass. This is not suppression of every mouse boundary event. |
| Pointer capture | Suppresses all `lostpointercapture` events through a window capture listener, regardless of target. | `main.js:103-108`; synthetic event probe confirmed blocking. Normal pointer-release/drag callbacks can be affected. |
| Animation | Proxies rAF: a call made while the isolated-world port says truly hidden is implemented with `setTimeout` and a `performance.now()` timestamp. It also clears timer IDs when cancelling while hidden, then always calls native cancellation. | `main.js:296-320`. A genuinely hidden run produced 3 callbacks in 1.3 s; timer throttling remains. A native rAF queued before hiding can stay suspended rather than reaching the fallback. This is not a guaranteed background frame rate. Cancellation across visibility changes remains a possible mismatch. |
| Fullscreen (optional) | **Off by default.** When enabled it installs own configurable standard/prefixed element and boolean getters plus fullscreen change/error listeners. It tries to return a cached fullscreen element while truly hidden. | `isolated.js:38,58-63`; `main.js:179-294`. Its handler refreshes the cache from the native getter before blocking, so an exit can replace the cache with null. Actual macOS tab-switch testing returned null/false and delivered fullscreen events despite the option. The baseline exited while still visible/focused before becoming hidden. It never keeps OS fullscreen. |
| Background redirect claim | Default `redirect=true`, but the implementation watches Navigation API **reload** events and conditionally installs a `beforeunload` prompt handler during a non-capture visibility listener. It is not a general URL/navigation blocker. | `main.js:48-76`. Its own visibility capture blocker normally prevents that arming listener. Ordinary background `location.href` redirects and reloads succeeded in controlled tests, with no prompt. Disabling visibility blocking could expose a different reload-prompt path; broad redirect protection is not established. |
| Per-host policy | Feature exceptions are read from `policies[hostname]`; same-origin children try the parent's hostname, cross-origin children keep their own. | `isolated.js:29-63`. Policies suppress named features, except the two unused getter checkbox options. |
| Immediate attachment | Toolbar activation can execute both scripts in existing frames without reload. Disabling a hostname does not remove already installed hooks; a reload is required to clear them. | `worker.js:115-133,239-294`; late injection preserved spoofed getters but earlier website blur/visibility handlers still ran. Non-configurable getters cannot simply be deleted. |
| Preferences/presentation | Local storage persists host/options; toolbar badges/titles indicate activation/reload. It can show a local onboarding popup and opens developer FAQ/uninstall pages in applicable install/update cases. | `worker.js`, options UI and manifest. These presentation/administration features are not required native website spoofing behavior; the native browser must retain its normal interface. |

The extracted code has no obfuscation. Inspection of the six packaged JavaScript
files found no fetch/XHR/WebSocket/eval-based exfiltration code; that is a bounded
static finding, not a general security guarantee. The manifest grants storage,
scripting, and ordinary HTTP(S) host access, which is enough to run the above
page modifications.

The native implementation deliberately operates at binding/event/scheduling
boundaries rather than installing these JavaScript tricks. Closing prototype
getter bypasses, suppressing events before window capture listeners, covering
all sites by default, handling pre-existing background rAF requests, and making
an optional hidden reload blocker effective are **native design improvements**.
They must be verified against built binaries and must not be presented as
behavior already demonstrated by the extension. The experimental hidden-only
fullscreen snapshot does not promise to retain a state already exited while
the document was still visible.
