# Native behavior patch

Implementation source: Chromium `156.0.8078.80`, commit
`fb096c0011f9d50f0a264a9376420cdea9c421e3`. The file URLs and original/patched
SHA-256 values are recorded in [provenance.json](provenance.json). This is a
native C++/Web IDL patch, not an extension, injected script, or DevTools helper.
No browser UI, extension implementation, Web Store permission, security origin,
site isolation, fullscreen permission, or user-activation code is changed.

## Controls and scope

These are Chromium `base::Feature` controls. They use the existing command-line
feature machinery and add no toolbar/settings/status UI.

| Feature name | Default | Effect |
| --- | --- | --- |
| `AlwaysActive` | Enabled | Master control; website bindings report visible/focused. |
| `AlwaysActiveEvents` | Enabled | Filter selected events from JavaScript listeners. |
| `AlwaysActiveAnimationFrames` | Enabled | Native timer fallback for background website RAF callbacks. |
| `AlwaysActiveFullscreen` | Disabled | Optional hidden-document fullscreen binding snapshot and event filtering. |
| `AlwaysActiveBlockBackgroundReload` | Disabled | Optional cancellation of eligible hidden top-level script reloads. |

Examples (append to this browser's ordinary launch command):

```text
--disable-features=AlwaysActive
--disable-features=AlwaysActiveEvents,AlwaysActiveAnimationFrames
--enable-features=AlwaysActiveFullscreen,AlwaysActiveBlockBackgroundReload
```

The master switch overrides every subfeature. Apply controls on a fresh browser
launch using this browser's own profile, not a stock Chrome profile.

Scope is active ordinary HTTP/HTTPS documents and their web-origin `about:`,
`data:`, `blob:`, and `filesystem:` documents where the real or precursor
origin identifies HTTP/HTTPS. HTTP/HTTPS sandboxed documents remain covered.
This is only a behavior selection rule and grants no origin access. Cross-site
frames retain separate processes/security origins and apply the same rule in
their own renderer. Browser UI (`chrome://` and similar), extension-origin
documents, standalone `file:`/opaque documents without a web precursor,
workers, detached/inactive documents, and prerenders retain upstream behavior.
The extension's host lists/per-host policy UI are not recreated: these controls
are global and ordinary extension support is left in place.

## Implemented semantics

`Document.idl` routes the JavaScript-facing `hidden`, `webkitHidden`,
`visibilityState`, `webkitVisibilityState`, and `hasFocus()` bindings to new
native getters. For an eligible document they return `false`, `false`,
`"visible"`, `"visible"`, and `true`. Native `Document::hidden()`,
`Document::visibilityState()`, `Document::hasFocus()`, page visibility,
FocusController, lifecycle state, and actual input focus remain unchanged.
The behavior applies before the first page script and to cached prototype
methods/getters as well as ordinary property access. It affects JavaScript in
isolated extension worlds too; there is no injected script's private real-state
port for an extension to consult.

Native event delivery skips JavaScript callbacks for:

- `visibilitychange`, `webkitvisibilitychange`, `pagehide`, and
  `lostpointercapture`;
- `focus` after the first event targeting that document or its window;
- `blur` and `mouseleave` targeting that document or its window;
- `mouseout` targeting that document's root element or body.

Element-to-element focus/blur, ordinary child-element mouse events, real pointer
capture bookkeeping, native event listeners, default actions, navigation,
BFCache, page freezing, and lifecycle processing continue normally. The filter
also applies to synthetic events with those types/targets. It does not install a
JavaScript listener, set `defaultPrevented`, or set propagation-stop flags.
Consequently, a synthetic cancelable event may have a different
`dispatchEvent()` return value than under the extension. Suppressed JavaScript
`once` listeners remain registered for a later unsuppressed event. The first
document/window focus event is retained as a GC-traced event reference so all
dispatch phases use the same decision. Re-dispatching that same synthetic focus
event object retains its first-event exception.

The RAF fallback is a GC-aware one-shot native timer on the existing JavaScript
high-nesting timer task queue, requesting a 16ms interval only while there are
pending web RAF callbacks and the document is really hidden. It uses the same
callback IDs/cancellation/snapshot collection as native RAF and timestamps from
the document's `performance.now()`. It does not drive internal frame callbacks,
CSS animations, video frame callbacks, rendering, or compositor work. Normal
foreground RAF continues through Chromium's frame scheduler. Background timer
throttling and context pause/freeze/destruction still apply. This is not a 60fps
guarantee, a way to run through OS sleep, or immunity from tab discard.

The optional fullscreen mode retains the last connected fullscreen element in
the document's GC-traced state when an actual hidden fullscreen exit occurs.
Only fullscreen binding getters (including prefixed aliases and the boolean
getters derived from them) use this snapshot while hidden, with normal
tree-scope retargeting. Fullscreen events are filtered from JavaScript while
actually hidden. Returning to the foreground exposes real state again and
resets the snapshot to current real state, avoiding stale state on a later
background visit. It
does not retain OS fullscreen, alter the top layer, grant permission/activation,
or suppress browser security UI. A removed element is never returned.

The baseline macOS runtime oracle observed tab-switch fullscreen exit callbacks
while native visibility was still `visible` and native `hasFocus()` was still
true, before the later hidden transition. Such visible-before-hidden exits
clear this optional snapshot and are **not protected**. There is no reliable
visibility/focus discriminator at that moment; the implementation deliberately
does not retain stale fullscreen state after a normal foreground exit or use
timing guesses. Natural tab-switch fullscreen state preservation on macOS is
therefore an explicit ordering limitation, not a demonstrated capability.

The optional background reload mode cancels a Navigation API `reload` event
only for an eligible actually hidden main-frame document, when the navigation
is renderer initiated and has no user-navigation involvement. It reuses the
existing native cancellation/abort path. It does not block server redirects,
`location.href`/`assign`/`replace`, meta refresh, links, form submissions,
history traversals, browser reload commands, tab closing, or subframe reloads.
It is disabled by default; do not advertise it as a general redirect blocker.

## Observed extension and deliberate differences

Reference artifact: Always active Window / Always Visible v0.4.8, CRX SHA-256
`17e792706dcc8d7b1ad236bd090b662ca97786c085594b35da421851a33b655b`.
The separate investigation/oracle report records the shipped source and runtime
evidence. The native patch follows its core promise rather than copying its
injection defects:

| Shipped v0.4.8 observation | Native choice |
| --- | --- |
| Own-document getters can be bypassed through cached prototype getters. | Patch the actual binding entry points; cached binding getters stay spoofed. |
| Visibility callbacks at window capture run before its document capture interceptor. | Filter selected JavaScript callbacks at every dispatch target/phase. |
| First visibility event may be allowed for a document initially hidden. | Suppress selected visibility callbacks from the beginning. |
| Already pending visible RAF callbacks can freeze when backgrounded. | Re-arm the native fallback on real visibility changes; preserve pending callback IDs. |
| Background RAF proxy uses `setTimeout` and was observed throttled. | Preserve background timer throttling and lifecycle freezing. |
| Optional fullscreen code refreshes its cache to null before attempting to block the exit event; runtime did not preserve state. | Optional binding snapshot deliberately fixes this cache defect without retaining actual fullscreen. |
| Redirect preference is on, but only watches reload and its own visibility interceptor can prevent the beforeunload listener from being armed; runtime reload/redirects proceeded. | Keep normal navigation by default; offer narrow native background script-reload cancellation as an explicit opt-in. |
| Visibility getter preferences are saved in options but not consulted by the shipped scripts. | Core getters follow the master feature; event/RAF modes have separate native controls. |

## Integration and evidence limits

For an unpacked source archive or a checkout, before GN generation/build:

```sh
python3 native/apply_patches.py --source /path/to/chromium/src --check
python3 native/apply_patches.py --source /path/to/chromium/src
python3 native/apply_patches.py --source /path/to/chromium/src --verify-applied
```

The applicator validates `chrome/VERSION`, every input/output SHA-256, exact
hunk context, and the patch digest. It needs only Python's standard library;
there is no `.git` requirement. It validates all files before writing, supports
idempotent application and partial-application recovery, refuses foreign edits,
and supports `--reverse`. `--allow-partial-source` is for selected-file local
authoring checks only. All changed sources are existing upstream build inputs,
so no GN target/file-list change is needed. Normal extension build flags must
remain enabled; this patch does not change them.

Local checks completed on the selected exact source files: Python syntax,
independent BSD `patch --dry-run`, digest/context validation, exact application,
idempotence, verify-applied, reverse dry-run, exact reverse round trip,
partial-application recovery, foreign-edit rejection without partial writes,
and wrong-version rejection. These establish patch mechanics only. **The C++
patch has not yet been compiled or run in a custom browser.** Build success,
native feature behavior, visual comparison, native Mac/Windows launch/signing,
and normal extension/Web Store compatibility require the GitHub-hosted builds
and native runtime tests; do not infer them from these static checks.

Future Chromium revisions require acquiring only the selected new source files,
reviewing implementation/API changes, regenerating the patch with
`native/make_patch.py`, updating provenance, and re-running actual builds and
behavior tests. Never apply with fuzz to a different revision.
