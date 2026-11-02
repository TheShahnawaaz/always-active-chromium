# Progress ledger

## Current state — 2026-11-02

There is no finished custom browser package yet. The exact-source **15-file**
native16 patch targets Chromium `156.0.8078.80`. It includes
visibility/focus/event/animation behavior, detached-document safety and optional
fullscreen/background-navigation controls and the pinned KURL method correction. Application/reversal/digest checks
pass; actual native C++ and runtime verification remain pending. The standard
interface and ordinary extension platform are retained in source.

| Target | Authoritative hosted state | Next action |
| --- | --- | --- |
| macOS arm64 | [Stage 1, run 41384338455](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41384338455) failed after **2,945/34,130** actions in that invocation: `document.cc:2382` called the nonexistent KURL method `ProtocolIsInHTTPFamily`. Its complete **8,104,577,408-byte** native15 checkpoint is verified. | Resume the reviewed native16 spelling correction from that exact cache, preserving compiled work. |
| Windows x64 | [Run 41384211984](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41384211984) passed real clean Rust/GN and the complete input audit, then failed compiling `swiftshader_libvulkan/Vulkan.res`: pinned `rc.py` could not find `build/toolchain/win/rc/win/rc.exe`. Early diagnostics and progress were verified; its checkpoint save remains live. | Preserve the save; review the exact pinned RC-hook repair, then resume with native16 and the repaired tool. |

The native16 correction changes exactly one source line to the pinned API
`ProtocolIsInHttpFamily()`, also used by upstream `document.cc`. The other 14
patched source records and all compiler pins remain identical. Ten patch checks
pass; root independently passed 16 migration/checkpoint-selection checks,
including both real native15 source sets and actual Ninja selective rebuilding.
The migration permits only Mac source `9f6d9a79aef2` / fingerprint `3ea184…` and
Windows source `697512488fc8` / `bc48a0…`; unchanged source/object bytes and mtimes
are preserved. There is no native14 or cold fallback. Native16 compilation and
runtime behavior are still unverified. Mac can resume independently while the
Windows tool repair is reviewed.

The Windows RC repair restores the exact DEPS `rc_win` hook: the missing
603,648-byte AMD64 compiler at `build/toolchain/win/rc/win/rc.exe`, verified against
its checked-in SHA-1, independent SHA-256 and immutable GCS generation. It does
not replace Microsoft's SDK compiler or alter Chromium's source driver. A real
post-GN smoke test will use the pinned Python/tool wrapper/environment and
compare a tiny compiled resource with the SDK compiler's output. Nine focused
repair guards and 15 existing build guards passed at root (one Windows-only
extractor integration skipped locally); actual hosted RC execution remains
unverified. Native16 fingerprints and the Mac path stay unchanged. The Windows
retry can queue behind the current save and restore its newest complete cache.

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
