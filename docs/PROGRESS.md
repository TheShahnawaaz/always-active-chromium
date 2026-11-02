# Progress ledger

## Hosted continuation — 2026-11-03 IST

**Mac verified development delivery is ready. Windows is still compiling.**
[41533441385](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41533441385)
passed fresh extraction, all behavior modes and 20/20 normal Store phases, then
produced the real 1000×677 native no-debug window image. Codex visually inspected
the complete standard Chromium shell and rendered fixture, with no added
always-active controls/banners. All seven evidence assets and six checksum
entries were independently verified. See [UI review](UI-REVIEW.md) and
[installation instructions](releases/mac-arm64/INSTALLATION.txt).

The [Mac draft download](https://github.com/TheShahnawaaz/always-active-chromium/releases/tag/untagged-4eebb053bab880d711db)
now links those records and exact checksums. The six original assets, including
ZIP and its five-entry manifest, are unchanged. Coordinator uploads to
`uploads.github.com` were network-policy denied, so documents/image are in the
repository and draft notes were updated through the permitted API. No policy
bypass, credential move, public release publication or new compiler job occurred.

Mac **41524595935** now passes compile, strict 16-part ad-hoc package sealing,
and core checks: baseline **32/32**, native **38/38**, optional **55/55**, paired
no-debug **7/7 each**. Its e146 ZIP is **252,685,495 bytes**, SHA-256
`7dbfafec37054e029848f1cedff431244b3031f96ae2cc6b076305119986d2b8`.
All six build assets and five checksum entries were independently verified.
The entire build is now green: **271/271** incremental actions completed, and
the six-part **9,901,553,400-byte** e146 compiler checkpoint is complete. Ready
asset 703318165 has SHA-256
`8da87fdafdc63eb430ddaa65fbe89ff2ab3687e6514b1a5fdef574ca515d7e83`;
its bytes, identity and every server part size/digest were checked.

Fresh-delivery [41529944500](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41529944500)
passed real extraction/signature/architecture/identity checks, all behavior
modes, and **20/20 normal Store phases** on the extracted custom app. Its five
delivery assets, all server digests/sizes and all four manifest entries were
independently checked. Package source remains `ci-source-e146fe41bca3`;
controller is `0728fb141cee`. Manual UI appearance review is still pending.
A guarded Mac owned-window capture is being added to the existing verifier.
Windows **41503529408** is still compiling; no healthy build was interrupted.

Capture-enabled [41531565373](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41531565373)
again passed all automated delivery/Store checks. Its assets and checksums were
verified. Permission preflights passed, but the window capture refused before
any image with `unique_owned_window_id_unavailable`. Visual review remains
pending. [41532536741](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41532536741)
now collects bounded metadata for that owned fixture window; helper compilation
and the invalid-PID refusal guard passed. This is a UI-evidence diagnostic on
the same real package, not another compiler build or a reference-Chrome trial.

That diagnostic run passed and identified one owned normal fixture window with
identical AX/CG bounds; only the full title strings differed between APIs.
Commit `68a55d8` checks both fixture titles independently and preserves both
strings in exact before/after state equality. Capture verification
[41533441385](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41533441385)
is now running; visual success remains pending actual pixels and manual review.

The continuation is running in the published cloud project environment.
Actual API checks at 02:46 IST (21:16 UTC November 2) show Mac
[41524595935](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41524595935)
restoring and Windows
[41503529408](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41503529408)
compiling. Both jobs were preserved, with no duplicate dispatch. Authenticated
draft-asset reads work in this runtime. The newest Mac ready-manifest bytes
and all six Windows preparation/input assets were independently hash checked.
Windows preparation is complete, and the audit records 75,790 checked leaves,
zero missing and no errors. Final package/runtime/Store/UI evidence remains
pending. See CONTINUE.md for exact observations and the next dependent actions.

The access probe [41527296038](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41527296038)
passed on standard hosted Ubuntu: dispatch, draft creation, asset roundtrip and
SHA-256 comparison, followed by temporary-draft deletion with the existing tag
preserved. At 02:53 IST Mac had also passed preparation/audit and begun its
incremental metadata rebuild. Windows was still compiling. No build was
restarted, cancelled or moved to another provider.

## Previous state — 2026-11-02, before hosted continuation

There is no finished custom browser package yet. The exact-source **15-file**
native16 patch targets Chromium `156.0.8078.80`. It includes
visibility/focus/event/animation behavior, detached-document safety and optional
fullscreen/background-navigation controls and the pinned KURL method correction. Application/reversal/digest checks
pass; the real Mac app has been packaged and exercised, with unresolved source
revision metadata and fullscreen test assumptions. Full delivery verification
remains pending on both platforms. The standard
interface and ordinary extension platform are retained in source.

| Target | Authoritative hosted state | Next action |
| --- | --- | --- |
| macOS arm64 | [41515581981](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41515581981), source `706479414249`, built and packaged the real app. All 16 Mach-O parts passed strict staged signing verification with source bytes/mtimes preserved. Actual core tests: baseline 30 pass/2 fail, native 37/1, optional 52/3; paired no-debug control 7/7 and native 7/7. The native-only failure is the upstream revision reporting zeros. Other failures assume a restored maximized window must be `normal`. A 252,684,636-byte draft ZIP exists with verified published checksums. Checkpoint save was still active at 20:56 UTC. | Incrementally rebuild with authenticated revision metadata, rerun corrected window-state checks, then verify a fresh extracted delivery, Store behavior and UI. |
| Windows x64 | Native16 [run 41395928784](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41395928784), source `1219c3c7eb27`, passed real RC preparation and audit, then stopped at **9,651/47,629** in V8 metagen: a standalone `gn desc` returned 1. [Retry 41503529408](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41503529408), source `81735e8f2ce2`, restored the verified **7,741,978,948-byte** native16 checkpoint, passed mandatory clean CPython/default GN-desc/RC preparation at 19:13:02 UTC and audited all **75,790** scoped leaves with zero missing. Compilation began at 19:13:47 UTC. | Preserve the live compilation and inspect its actual next result. |

The 18:53 UTC official version check still identifies `156.0.8078.80` as
Chrome for Testing Stable and the pinnable, fraction-1 Stable release on both
[Mac arm64](https://versionhistory.googleapis.com/v1/chrome/platforms/mac_arm64/channels/stable/versions/all/releases?filter=endtime%3Dnone)
and [Windows x64](https://versionhistory.googleapis.com/v1/chrome/platforms/win64/channels/stable/versions/all/releases?filter=endtime%3Dnone).
The higher `157.0.8103.26` entry is a non-pinnable 0.005 rollout, not the selected
full Stable release. Source pins and the native16 fingerprints remain unchanged.

The Mac run now establishes actual native default behavior on the staged app;
it does not establish a verified final installer. Its ZIP SHA-256 is
`5d3e2f23fca62e07c4d2ea26e69ce467ffd8ddc3d0ea8dab82b36b9ed2392252`.
The source revision failure comes from upstream's nonofficial
`use_dummy_lastchange` default. The repair authenticates the actual pinned Git
commit and generator inputs, emits standard LASTCHANGE metadata, and explicitly
selects it with the supported GN argument while keeping official/branding flags
false. Seven focused tests pass, including the real pinned version generators.
Fullscreen checks now accept only `normal` or `maximized` on the exact expected
window; four focused tests reject fullscreen, minimized, unknown or wrong-window
results. CSS state, binding snapshots, event suppression and focus checks remain.

The user requested laptop-independent work. GitHub jobs and their configured
bounded continuations already run remotely. The initial Cloud sign-in rate limit
was resolved by the user. Project-only environment onboarding validated the
e146 checkout (147 Python passes, 13 skips; 67 Node passes, one skip) and prepared
a private environment. Publication is now confirmed in the Cloud environment
picker as `always-active-chromium`; GitHub API permissions still need rechecking
in the task runtime. The user chose to hand the goal to Dot, so no separate
continuation coding task was launched. See [Dot's goal and handover](CONTINUE.md);
do not claim Dot has started until its actual task is running.

The metadata/window-state fix is pushed at `e146fe41bca3`, with source and both
final package tags. [Mac retry 41524595935](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41524595935)
is running since 21:01:59 UTC. The prior Mac run is terminal and its newest
complete six-part checkpoint totals **9,900,445,822 bytes**; ready asset
703165989 has SHA-256
`00c430daf2ecfbda592033547b82fa3f395a36755f1628e014a891ecdd890463`.
Its manifest and all server part sizes/digests were verified. The new run uses
exact restoration with `migrate_native=false`; no full rebuild or native/config
repin is intended.

The initial measured complete checkpoint saves took 19m12s–25m33s. The final
9.90 GB Mac cache subsequently took **31m34s** and remains the observed maximum.
Future source raises the
absolute compile budget from 220 to 270 minutes, retaining a 90-minute tail
inside the same six-hour standard-runner limit. Live immutable campaigns keep
their existing budget and completed work; they are not restarted for this change.

The native16 correction changes exactly one source line to the pinned API
`ProtocolIsInHttpFamily()`, also used by upstream `document.cc`. The other 14
patched source records and all compiler pins remain identical. Ten patch checks
pass; root independently passed 16 migration/checkpoint-selection checks,
including both real native15 source sets and actual Ninja selective rebuilding.
The migration permits only Mac source `9f6d9a79aef2` / fingerprint `3ea184…` and
Windows source `697512488fc8` / `bc48a0…`; unchanged source/object bytes and mtimes
are preserved. There is no native14 or cold fallback. Windows native16 compilation
remains unverified. The complete Mac compile and its later partial runtime results
do not establish a finished delivery.

Mac packaging now prepares a fresh independent app copy, inventories actual
Mach-O/signature metadata, and signs inside-out using an ad-hoc identity only
for the accepted unsigned/linker-ad-hoc baseline. Existing entitlements and
enforcement flags must remain equal; stronger flags or non-ad-hoc identities
are refused rather than downgraded. Compiled bytes and file/directory/symlink
mtimes must remain unchanged. No development entitlement, new signing option,
private certificate, notarization or OS security change is introduced.
Strict verification remains required for each part and the complete app.
Core browser checks use the same staged executable that is archived. Seven
real tiny C/app/framework fixture tests pass at root, including the production
packaging/extraction path and unchanged executable hash after the ZIP roundtrip;
these are not Chromium runtime tests. Seven bounded diagnostic guards and 15
existing build checks pass (one Windows-only check skipped locally). Fixed
bounded signing JSON is published before a long checkpoint so future packaging
failures can be inspected promptly. Run 41515581981 subsequently verified actual
Chromium signing and exercised the staged app, as recorded above.

The Windows RC repair restores the exact DEPS `rc_win` hook: the missing
603,648-byte AMD64 compiler at `build/toolchain/win/rc/win/rc.exe`, verified against
its checked-in SHA-1, independent SHA-256 and immutable GCS generation. It does
not replace Microsoft's SDK compiler or alter Chromium's source driver. A real
post-GN smoke test will use the pinned Python/tool wrapper/environment and
compare a tiny compiled resource with the SDK compiler's output. Nine focused
repair guards and 15 existing build guards passed at root (one Windows-only
extractor integration skipped locally); the actual hosted RC preflight subsequently
passed in run 41395928784. Native16 fingerprints and the Mac path stay unchanged. The Windows
retry can queue behind the current save and restore its newest complete cache.

The standalone V8 `gn desc` rereads `.gn` without the `--script-executable`
override used by `gn gen`. A tiny fixture with the real pinned GN reproduced
that distinction; V8's wrapper drops GN stdout containing the useful error.
The exact runner's CPython residue remains unverified. A clean, exact-pinned
Windows CPython package and default-interpreter/GN-desc preflight are ready
without editing Chromium's `.gn` or V8. Ten focused Python-host tests and 15
existing build checks pass at root (one Windows-only integration skipped).
The GN JSON validator accepts its exact qualified or default-toolchain label
only with the expected Windows toolchain. Its native16 fingerprint stays
unchanged so the completed Windows objects remain reusable. Actual host
execution has now passed that mandatory preparation and the input audit in
run 41503529408. Its six bounded assets, all server digests and four checksum
entries were verified against exact source/workflow `81735e8f2ce2`. This does
not prove compilation or browser behavior. Prior CPython headers remain
unobserved until the live job's console logs are available.

Real Windows Rust pre-clean evidence is now available from the prepare step,
separately from unit fixtures: extensionless `rustc` was a 315,608-byte ELF,
while `rustc.exe` was a 119,296-byte MZ file. The clean-host remediation and
mandatory executable/host/stdlib checks passed. The earlier ELF-shadowing
hypothesis is therefore observed for Rust; that does not by itself prove the
CPython cause.

The previous Windows retry
[41377808648](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41377808648)
verified all 96 files in the two exact-pinned Microsoft source dependency roots,
passed preparation/GN, and completed the scoped declared-input audit: **75,790
leaves checked, zero missing**, complete result, no audit errors, 24.735 seconds.
The graph and leaf-list sizes were 144,611,224 and 85,739,961 bytes. Audit/status
asset hashes and their checksum manifest were independently verified. This
scope excludes compiler-discovered headers.

Ninja then stopped in `build/rust/std/find_std_rlibs.py` at its extensionless
`bin/rustc` subprocess with **WinError 193**. Two other actions completed, so the
resulting five-part **7,774,697,184-byte** checkpoint was saved and verified
complete. Its tag is
`checkpoint-win-x64-bc48a05d11339f14ef8f-41377808648-1`.
A stale foreign-host extensionless compiler is a hypothesis until the new
preflight records the actual previous binary headers. The repair follows
upstream replacement semantics: stage a clean hash/size-verified Windows Rust
package, verify AMD64 PE and exact release/commit/host, execute both rustc.exe and
the exact extensionless standard-library query through pinned CPython, then
atomically swap with rollback. Revalidated clean packages preserve file mtimes.
It does not patch Chromium's upstream Rust build scripts or native behavior.

The corrected Windows run has now passed that mandatory real-host Rust
preflight, including PE/release/host/commit and the exact extensionless
standard-library query. Its early prepare report is complete with no events;
the next audit again checked **75,790 leaves, zero missing**, complete=true,
in **24.235 seconds**. Both phases' six assets, four JSON checksums and exact
source/workflow identities were verified. Compilation continued beyond the
former nine-second failure. The actual old binary headers remain unverified
until console logs are available; ELF-shadowing is still a hypothesis.

The Mac campaign restored the previous complete **7,566,257,986-byte** checkpoint,
which had completed **10,753 of 57,570** actions before discovering Dawn's
missing nested Go tool. The current source hydrates the exact Dawn Go package
and verifies its absolute executable version/host before GN. Those hosted
checks passed. The next stage completed another **12,688** actions in its resumed
invocation before the time budget. Its five-part **8,029,991,859-byte** checkpoint
manifest, all part digests/sizes and source/native identity were verified.
The automatic continuation at 03:40:04 UTC uses the same older immutable source
and workflow, so the newer CI-only speed changes do not apply to that campaign.
The obsolete native14 final tags were removed; approved old
checkpoints remain cache inputs only. Migration is opt-in and validates exact
source hashes and unchanged build pins. No obsolete browser was delivered.

Commit `6975124` shortens the retry/delivery cycle without changing either native
fingerprint. Future-source runs publish fixed bounded tool-preflight and compiler
JSON before large checkpoint uploads. On an exact restore without migration,
a normal failed compile can skip a duplicate upload only with a conservative
pinned-Ninja proof that no command actions completed; uncertain cases still save.
Real Ninja fixtures prove successful actions invalidate that shortcut. Completed
packages and existing core/optional/MV3/no-debug evidence are now published to a
truthfully labeled draft before the potentially long checkpoint save. The live
older Mac job retains its already-frozen ordering.

The combined CI suite passes **72 local tests** (one Windows-only extractor
integration skipped locally, previously passed hosted). Root independently
rechecked the new **13 Rust** and **6 diagnostic** tests, including actual pinned
Ninja fixtures, plus workflow syntax and unchanged native fingerprints. These
checks establish CI mechanics, not native browser behavior. Original CFT passed
7/7 passive no-debug control checks and correctly failed native expectations;
the actual native paired checks remain required on both built packages.

The full normal Store controller uses a distinct owned profile, normal Store Add,
a separately verified native permission action, audited installed uBOL source,
actual worker responses, normal restarts, an ordinary update request, normal UI
removal, another restart and normal final close. The reference runs establish
mechanics on official CFT only, never native-browser compatibility.

[Run 41381085404](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41381085404)
passed 19/20 checks on each platform, including every functional operation above.
Its final old ID-entry predicate rejected a remaining **exactly empty dictionary**
in Secure Preferences. Bounded complete shape evidence and the pinned Chromium
registration readers establish that this empty value is neither an installed
startup registration nor a pending installation; its writer remains unknown.
The corrected check separately records physical identifier-entry presence and
persisted registration absence, allowing only missing or completely empty
entries. Nonempty, malformed, pending and unknown records still fail; native
removal, live/restarted absence and normal close remain mandatory. All 41 offline
controller policy tests passed. Historical reports retain their original status.

The final corrected reference
[run 41384092270](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41384092270)
at `43c9cd2` passed **20/20 phases on both platforms**. All eight bounded assets,
GitHub digests/sizes, checksum manifests and exact controller identity were
independently verified. These are CFT reference results only. See
[the evidence ledger](oracle-evidence.md) and
[Store compatibility plan](../tests/STORE-COMPATIBILITY-PLAN.md) for exact coverage.
A `no_update` response does not establish server transport or an actual newer
Store version transition. Actual native-package Store verification and a genuine
version transition remain unverified.

A focused coverage follow-up at `ffa902f` added explicit cached native binding,
prefixed alias and visible-started animation-chain assertions. Hosted
[run 41384856723](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41384856723)
passed **baseline 32/32 and shipped oracle 37/37 on each OS**, including all four
new assertions. All 14 assets, hashes/manifests and controller identity were
verified. The controls were genuinely hidden, and their existing animation
chains remained frozen after settling. Native mode must separately prove its
intended binding and continued-animation differences on actual packages.

The reviewed delivery workflow is now implemented for actual future package
drafts. It verifies exact source/final refs, source pins/native fingerprint,
package and build-manifest hashes, then extracts the Mac ZIP with `ditto` or
runs the real Windows per-user mini-installer on a fresh hosted runner. The
existing four behavior modes and full normal Store controller receive that
installed/extracted executable. Canonical executable path, size and SHA-256 bind
the reports to acquisition, with an unchanged-executable check after behavior
tests. Failed, partial, timed-out or uncertain evidence cannot produce verified
status, and a failed verification returns a failed workflow after retaining its
bounded JSON receipt. No profiles/raw logs are published by this verifier.
All **20 focused delivery tests** and the existing **four cleanup tests** passed
at root, together with Python/workflow syntax and unchanged native fingerprints.
Actual delivery execution remains pending until the real packages exist.

To verify the explicit desktop-appearance requirement, Windows delivery now
requests one optional owned full-window image during its existing native
no-debug phase, after passive behavior observations and before verified cleanup.
A separate helper rechecks PID/executable/profile/creation/SID/session and the
unique normal foreground HWND before and after one bounded `PrintWindow` call.
There is no desktop fallback or input/debugging action. PNG integrity and
identity are validated; capture failure stays distinct from runtime/Store
results. Every retained image remains pending manual visual review, with no
UI-equivalence or complete-pixel claim. Root passed four Node guards (one
Windows-only guard skipped locally), six Python image guards, two reference
publication guards and the 20 delivery guards, plus syntax/diff checks.
The first reference-only [run 41390391923](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41390391923)
at `c0a0da4` failed **before capture**: both Windows CFT control pages sent zero
accepted or rejected posts over 45 seconds. Only the normal CLI, absent debugging
port and owned cleanup checks passed (3/7). All four retained assets and the
three-entry checksum manifest were verified. No PNG/receipt exists, and the
capture helper was never called; this does not establish a PrintWindow failure.
The underlying startup/reporting cause is unknown. The reviewed follow-up now
records finite navigation counters and a failed-run-only read-only owned-window
startup diagnostic. It starts state reports independently of the UA version
promise and explicitly records pending/resolved/error version state. Four
fixture tests pass, including an unresolved version promise; the full-version
assertion and resolved matching-version requirement remain mandatory. The next
trial will establish whether pages navigate and execute before any capture.
Capture reliability and actual custom-package appearance remain unverified.

The second [run 41391883284](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41391883284)
at `cd920e4` again stopped before capture. Its new counters establish **zero HTTP
requests of any kind**, including zero page GETs, so neither test page was
fetched. The identity-reverified owned window was **Untitled - Google Chrome
for Testing**. Both version statuses remained no-report. All four assets and
three checksum entries were verified, and owned cleanup passed. This does not
support a UA-lookup delay as the cause. The reviewed next diagnostic classifies only owned direct-child roles and
bounded owned-window address/error state, with target-window visibility,
minimization and foreground booleans. It keeps finite partial snapshots if UIA
stalls and never retains raw UI trees, addresses or child command lines.
Eight sanitizer/fixture guards and source/workflow syntax checks pass; actual
Windows PS5/UIA execution remains pending the next trial. No product, launch-flag,
focus, security or assertion changes are made to obtain a pass.

Both real launchable packages, native behavior/no-debug evidence, installation
checks and actual-package Store compatibility are still required for completion.
Stock Chrome and its profiles remain untouched. All build compute remains on
standard GitHub-hosted runners, with no AWS, external builders or paid upgrades.

The third Windows reference trial 41393878708 verified a foreground, visible,
nonminimized owned CFT window at the expected loopback address, with five
renderers and a network utility among nine verified children. UIA found no
allowlisted error tags. Parsed HTTP counters still remained zero, and no capture
was attempted. All finite assets/checksums and cleanup were verified. This does
not prove zero TCP connections: request callbacks and TCP accepts are distinct.
The reviewed next diagnostic adds bounded accepted-socket/byte/close counters
and a separate 2-second controller health GET before launch. Controller traffic
is excluded from observation counters; later connections remain explicitly
unattributed. Fourteen guards pass, including real local HTTP/TCP cases. Browser
flags and acceptance checks remain unchanged; actual Windows startup/capture
cause is still unresolved.

The fourth reference trial
[41503536129](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41503536129),
source `81735e8f2ce2`, measured a successful dedicated controller health GET:
HTTP 204 in 11 ms, source-port matched, one accepted/closed socket and one
request, excluded from observations. Prelaunch and post-launch unattributed
buckets both had **zero accepted TCP connections, bytes and requests**, with
complete unsaturated tracking. This establishes a working listener/self-request
but does not prove whether Chrome attempted a connection blocked before
acceptance. The owned foreground window remained Untitled at the expected
loopback address; nine verified children, no allowlisted UI error tags, and
cleanup passed. All four finite assets and three checksum entries were verified.
No capture was reached, so no PNG or capture receipt exists. This is still a
failed reference test and supplies no native-package proof.

The fifth reference trial
[41506801324](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41506801324)
reached one read-only capture on the freshly reverified owned foreground Untitled
window. Flags-0 `PrintWindow` produced a solid image, correctly refused before
PNG publication. All five finite assets/four checksum entries were verified.

The sixth trial
[41507767490](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41507767490),
source `32a2b2891343`, changed only the capture method to full-content flag 2.
It retained a validated **1044×788, 20,858-byte** diagnostic PNG, SHA-256
`f3065774b567851170799d8576c987f515906f60eea6c5b103bc56bfd256880d`.
All six assets/five checksum entries and embedded PID/executable/profile/start,
owner/session, foreground HWND and before/after title/geometry proof were
verified. Root inspected the actual pixels: Chrome controls and the CFT notice
are visible, both tabs say Untitled, the expected test URL is displayed, and
the page body is white with no visible error page/dialog. No complete-rendering
or UI-equivalence claim follows from that image. Health passed again while all
post-launch TCP/HTTP counts remained zero. The run and behavior remain failed;
the image is explicitly `startup-diagnostic`, `behaviorVerified=false` and no
native browser package is established.

A bounded audit of the pinned CFT startup/banner/config/network branches found
no intentional requirement for an attached debugger before ordinary navigation.
The notice is informational; its optional required-components startup wait is
inactive with the fresh-profile trial's default configuration. This does not
identify the observed hang or establish that it is CFT-only. The native build
uses the separate upstream
[`is_chrome_for_testing=false` default](https://github.com/chromium/chromium/blob/fb096c0011f9d50f0a264a9376420cdea9c421e3/build/config/chrome_build.gni#L19);
the pins do not override it, and `build/BUILD.gn` therefore sets
`CHROME_FOR_TESTING=false`. Root inspected those exact selected source files and
the renderer of GN arguments. The CFT notice/config/startup branches are excluded
by configuration, independently of branding. The next required evidence is
ordinary startup and behavior on the actual native packages; no further reference
trial is justified by this source audit alone.

The older entries below are historical observations. The state above takes
precedence over their former "current" campaign labels.

Goal: native always-active desktop Chromium with its standard interface unchanged,
ordinary extension support preserved, and verified macOS arm64 and Windows x64
packages. All compilation must run on standard GitHub-hosted runners; no AWS or
other external/self-hosted compute and no additional spending is authorized.

## Confirmed

- Public repository created with user approval.
- Current stable Chrome for Testing version at 2026-11-01T09:13:00Z:
  `156.0.8078.80`, revision `1706539`.
- Chromium release tag `156.0.8078.80` resolves to
  `fb096c0011f9d50f0a264a9376420cdea9c421e3`.
- GitHub-hosted runner preflight run `41348658261` completed successfully.
- macOS runner measured 3 CPUs, 7 GiB RAM and approximately 96 GiB free disk
  before cleanup, with Xcode 26.6 and macOS SDK 26.5. Windows measured 4 CPUs
  and approximately 16 GiB RAM. Corrected preflight run `41349098782` confirmed
  approximately 220 GiB free on Windows D: and 27.7 GiB on C:, Visual Studio
  2026 version 18.11.3 and Windows SDK 26100.
- Official Chromium source archive for the exact version is available and
  measures 4,422,962,028 bytes compressed; a full local Git clone is unnecessary.
- Full source/build outputs are not being downloaded onto the local Mac.
- Extension source and REA evidence from the initial investigation are retained
  locally, outside the public repository. The binary implementation and
  behavioral verification are still pending.
- Native C++/Web IDL patch committed as `74613f1`: 13 exact upstream source
  files, with unchanged browser UI and extension implementation. The applicator
  validates the complete source set before writing. Independent patch dry-run,
  apply/verify/idempotence/reverse, partial recovery and wrong-input rejection
  checks passed. C++ compilation and native runtime behavior are not verified.
- Resumable GitHub-hosted pipeline committed as `8917a4a`. Five checkpoint
  tests passed locally, including exact timestamp preservation, actual Ninja
  no-rebuild restoration and safe exclusion of generated absolute SDK links.
- First hosted bootstrap run
  [41350730760](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41350730760)
  verified the official source archive download on both targets. Windows'
  native tar later failed with an empty/unreadable filename diagnostic. This
  obsolete bootstrap was cancelled after storage/provenance fixes; no compiled
  browser objects or reusable checkpoint were produced by it.
- Initial hosted reference run
  [41350893756](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41350893756)
  passed measurements on both OSes but failed report publication because of
  GitHub's workflow-commit release permission guard. Source tags alone did not
  resolve that guard. Checkpoint/reference release tags now act only as storage
  anchors; metadata records the actual checkout and source pins. Final binary
  releases require pre-created exact source tags and omit target overrides.
- Hosted reference run
  [41351983527](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41351983527)
  fully succeeded on both OSes: 21 baseline and 28 shipped-extension assertions
  per platform, plus draft report publication. All six checksummed report/log/
  provenance/status assets on each platform were downloaded and verified.
  These are reference results, not custom native-browser results.
- Full auto-resuming build run
  [41351980824](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41351980824)
  used immutable project source `2015fd2a2eeb`. Mac passed source/toolchain/native
  patch/GN preparation and entered Ninja at 21:42:19 UTC. Windows stopped before large downloads because
  Git checkout CRLF conversion changed fingerprint bytes. Commit `9ffdca6`
  enforces LF across platforms. This diagnostic campaign was superseded before
  a completed browser existed so both targets could use the final startup fix.
- Windows extraction probe
  [41353041394](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41353041394)
  reproduced the source failure on valid CJK/emoji PAX names with Windows
  bsdtar 3.8.9. Bundled Git GNU tar 1.35 passed Unicode, long-path and native
  symlink/hardlink cases. Windows source extraction now uses that proven path
  with strict failure handling and records the selected tool in provenance.
- Current full auto-resuming run
  [41353967689](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41353967689)
  uses immutable source `67dea4dbe7e2` and a 14-file patch. It includes consistent
  LF inputs, the Windows GNU extractor, and omission of the unbranded-build
  missing-Google-API-key startup notice. API availability and all security/OS/
  encryption warnings remain unchanged. Both exact final-release Git tags were
  created before dispatch. Compilation/package results are pending.

## Work in progress

- First hosted compilation and native behavior verification of the written patch.
- Actual source/toolchain/GN and resumable compilation results for the current
  14-file campaign on both platforms.
- Toolchain hydration and resource-aware runner preparation.

## Not yet established

- Whether the constrained hosted runners can finish both full builds with the
  available disk, memory, time and free storage allowances.
- Whether every optional extension behavior has a useful native equivalent.
- Browser binary artifacts, native behavior test results, extension compatibility
  results, signing and distribution results.

Do not mark the goal complete from source changes or successful preflight alone.
