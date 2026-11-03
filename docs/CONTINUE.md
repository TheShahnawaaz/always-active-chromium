# Continue the browser delivery

## Goal for Dot

Complete and deliver a Chromium browser for macOS Apple Silicon and Windows x64
that looks as close as legally and technically possible to the pinned current
Chrome interface and implements the investigated Always Active Window 0.4.8
behavior natively, enabled by default for ordinary websites and frames. It must
work in everyday use without an extension, injected script, debugging connection
or local helper, while retaining ordinary modern extensions and Web Store use.
Finish the existing implementation rather than starting over. Use standard
GitHub-hosted builds only; never AWS/AWS Mac, external/self-hosted builders,
paid runners, plan upgrades or paid storage. Keep the user's stock Chrome and
profiles untouched.

Success requires actual installable packages for both targets, passing native
behavior checks on fresh extracted/installed deliveries, verified ordinary
extension installation/execution/restart/update-check/removal, reviewed native
UI evidence, checksums and clear installation/limitations documentation. Keep
branding, Google-service restrictions, signing and update differences explicit.
Do not declare success from patches, fixtures, reference Chrome, a compile or
an unverified package. Investigate and fix failures; report a measured blocker
if the authorized route cannot proceed.

The hosted continuation is now active in the published project environment.
Its coordinator has read this handover and checked actual GitHub runs and draft
assets. The existing GitHub builds continue with the laptop off. Before any
dispatch, inspect current runs and avoid another coordinator or duplicate build.

Read `AGENTS.md`, `README.md`, `docs/PROGRESS.md`, `ci/BUILD.md` and
`native/BEHAVIOR.md` first. Finish the existing goal: installable macOS arm64
and Windows x64 Chromium with native always-active behavior and ordinary modern
extensions, using the standard UI. Do not declare completion from source,
fixtures, a compile, a package, or reference Chrome results alone.

## Compute and access

- Browser compilation must use the existing **standard GitHub-hosted** workflows
  only. Never AWS/AWS Mac, external/self-hosted builders, paid runners, upgrades
  or extra paid storage. Do not download the full Chromium source into a cloud
  coordinator or the user's laptop. Small source snapshots/scripts/tests are OK.
- Preserve the user's stock Chrome app, profiles and extensions. Native browser
  tests/installations must use only task-owned apps/profiles and existing guards.
- Commit, push, immutable tags, workflow dispatch and draft release operations
  for this public project are authorized. Do not publish credentials or copy
  local CLI/ChatGPT auth files. Check actual GitHub integration capabilities;
  lack of Actions/release access is a blocker to report, not a reason to claim a
  successful handoff or secretly move a broad token.

## Current source and observed results

**Verified native development installers for both platforms are delivered.**
No further browser rebuild is required for this delivery. The user's Mac focus
report was caused by opening the demo as a standalone file document. The user
confirmed it works when served over loopback HTTP and explicitly accepted
HTTP/HTTPS scope without file:// support. Native behavior and Mac bytes remain
unchanged; no Mac diagnostic/rebuild was dispatched for that resolved report.

- **Mac Apple Silicon:** unchanged source `ci-source-e146fe41bca3`, build
  41524595935, final fresh delivery 41533441385. ZIP **252,685,495 bytes**, SHA-256
  `7dbfafec37054e029848f1cedff431244b3031f96ae2cc6b076305119986d2b8`.
  Download: https://github.com/TheShahnawaaz/always-active-chromium/releases/tag/untagged-82fe1e763809e6742669
- **Windows x64:** corrected source `ci-source-07fb6c3f9ed7`, full commit
  `07fb6c3f9ed75340048ae6aeb0df5696c5b59fde`, core/build 41657571863, final fresh
  delivery **41663769161**, controller `d3cbe0964f4e204ceabcc782ad75c71fbe035c44`.
  Installer **215,424,512 bytes**, SHA-256
  `4e0ae88f4b45b1ea5e6c1725320fb5a851a25c63e42c299889dee2963aba0ad3`.
  Download: https://github.com/TheShahnawaaz/always-active-chromium/releases/tag/untagged-fde85267f992fce5ce86

Both actual delivered apps pass baseline **32/32**, native **38/38**, optional
**55/55**, paired no-debug control/native **7/7 each**, and **20/20** normal
uBlock Origin Lite Store phases. Actual native window images were visually
reviewed: standard Chromium controls and rendered fixture, no new always-active
UI. Mac's original 1000×677 image is unchanged. Final Windows image is 1044×788,
asset **706095670**, 24,357 bytes, SHA-256
`b8fc371bfbe5de081acbaa416477e550d264adedc211739bbc2ee06efa495d19` in delivery
draft **432879456**. All six build assets/five manifest entries per platform,
and seven final delivery assets/six entries per platform, were independently
verified. Instructions, separate visual reviews, provenance and shared installer
checksums are in `docs/releases/`; see `docs/UI-REVIEW.md` for actual pixels.
Draft downloads require repository release access; stable tag-based CLI download
commands are included because draft web URLs can change when notes are edited.

The original Windows run 41638453497 compiled/packaged but failed its uninstalled
build-tree core checks: AppContainer could not read/execute the build-directory
chrome.exe (0x5), causing sandbox-policy startup failure. Original reports and
assets remain unchanged. The corrected workflow now installs the actual package
through guarded default per-user installation before core tests. Its published
`workflow_test_outcome` is **success**, all four modes pass on the installed app,
and the manifest records real installation/x64/version and executable hashes.
The installer is byte-for-byte identical to the earlier dd4dfe package. The
installed executable remains 4,200,448 bytes, SHA-256
`a622201cb3501ea22b2851878f144c2a70270bccc58cef333f8bcfa6727030b4`.
No sandbox, browser flags, compiler pins, native source or fingerprint changed.
All 148 local Python tests pass (15 platform/tool/source skips); hosted core and
final installed/Store checks validate the fix, rather than an effective REST label.

**Nonblocking checkpoint backup remains active as of 15:43 UTC / 21:13 IST.**
Preserve [41657571863](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41657571863).
Compilation, real installation, core verification and package/evidence publication
have completed; only its completed-output backup is running. Draft **432870875**,
tag `checkpoint-win-x64-cfc3210920f1d83aa4ac-41657571863-1`, had three full parts
and no ready marker at that observation. Do not call it complete yet or cancel
it. Its eventual ready manifest should be byte/hash/identity/part verified if
continuing archival supervision. This does not block the verified installers.
The prior complete six-part **10,669,016,313-byte** cache is draft **432797322**;
ready asset 705955160 (6,192 bytes), SHA-256
`316cedd7a10bd83ab5d88ed3ae79fd247feb7f025243b942e42e9e179fcf6f5a`, was verified
against exact native/version/revision/source, complete state and all part server
digests/sizes. It remains a fallback until normal new-generation cleanup.

Only standard GitHub-hosted runners were used; no AWS, external/paid builders,
upgrades or extra paid storage. No healthy compile/save was cancelled or blindly
duplicated. Mac is ad-hoc signed (strict verification of all 16 parts), without
Developer ID/notarization; Windows has no Authenticode certificate. Updates are
manual. `no_update` verifies a completed ordinary Store check, not a real newer
version upgrade. Coverage remains finite and no proprietary Chrome pixel/service
equality is claimed. Stock Google Chrome and its profiles remain separate.

The coordinator execution gap was resolved at 13:03 UTC, with no credential or
network-policy change. Its successful standard-hosted read-only audit 41638507119
and finite receipt `docs/evidence/windows-41598060999-audit.json` remain history.
The temporary audit workflow was removed after it served its purpose. Current
CLI execution works and no clarification or additional approval is pending.

## Earlier observations (historical; current state is above)

The following records describe earlier observations, not current dispatch or
waiting instructions. In particular, Mac visual review is now complete and the
older Windows runs are terminal.

Fresh actual-package delivery **41529944500** also passed, controller
`0728fb141cee`, source still e146. Draft **431998425**, tag
`delivery-verification-mac-arm64-41529944500-1`, contains all five independently
hash-verified delivery assets. The extracted arm64 `org.chromium.Chromium` app
passes strict signature verification and all four behavior modes. All **20/20**
normal uBlock Origin Lite Store phases pass, including source audit, worker
execution, restarts, ordinary update check, native UI removal and cleanup.
The executable SHA-256 is
`593391740bc2ebfc205148734c1f2b7be66a3fc1ef50987665003bb7afd8424b`.
The updater's `no_update` does not establish a genuine newer-version transition.
**Manual UI appearance review remains pending**; the first delivery run did not
request a Mac image. The continuation adds a guarded, permission-preflighted
Mac window capture to the existing verifier for that remaining evidence.
Windows 41503529408 remains in its existing compilation; preserve it.

**Windows update at 03:57 IST November 3 (22:27 UTC November 2):** run
41503529408 reached its configured compile budget and is saving a checkpoint.
Actual compiler diagnostics say `status=pending`, `exit_code=2`, complete
capture, no events, `normal_failure=false`, `logging_error=false`; the compile
step outcome is success. Its valid pinned-Ninja log grew from 5,339,384 to
8,121,013 bytes, so completed work must be retained. All three diagnostic assets,
server sizes/digests and two checksum entries were independently verified.
The new draft is **432035409**, tag
`checkpoint-win-x64-cfc3210920f1d83aa4ac-41503529408-1`; it had no ready marker
at that observation and must not yet be selected as a complete cache. Preserve
the save and the configured automatic continuation. Do not dispatch a competing
Windows job or cancel the chain to change its immutable source.

The capture-enabled fresh delivery **41531565373**, controller `308e8c6fe592`,
also passed acquisition, all behavior modes and Store compatibility. Its five
assets and four checksum entries were independently verified. Both existing
screen-capture and accessibility preflights passed, but the helper refused
before capture with `unique_owned_window_id_unavailable`: the focused AX fixture
window did not uniquely match the stricter window-server filter. No image or
visual success was claimed. **41532536741**, controller `8f6f44b40a29`, is the
active diagnostic verification of that same e146 package. The Swift helper and
invalid-PID refusal guard passed; its bounded owned-PID-only metadata receipt
will identify which title/bounds/layer comparison failed. Inspect that actual
receipt before changing the match; no permission, desktop capture or security
setting workaround is needed or authorized.

The diagnostic **41532536741** passed all delivery/Store checks and its assets
were hash verified. Its receipt shows one owned layer-0/alpha-1 window, exactly
matching AX bounds (22,31,1000,677). Both API titles identify the fixture, but
the full strings differ. Commit `68a55d8132e9` validates each fixture title
independently, retaining both full strings plus exact ID/bounds in before/after
state equality. Actual capture verification **41533441385** is running against
the same e146 ZIP. No browser source, compiler pins or native fingerprint changed.

Chromium is pinned to `156.0.8078.80`, upstream
`fb096c0011f9d50f0a264a9376420cdea9c421e3`. The native16 patch has not changed.
Native fingerprints remain:

- Mac: `c9ac6366f39a2bdd17c34d4d7312487a82e4a31002ea6491494bd652016dc2e1`
- Windows: `cfc3210920f1d83aa4ac25d5b69f54dd7b611c4df44b91dceb1a61d12c36468a`

Mac run **41515581981**, source `ci-source-706479414249`, built a real app,
strictly sealed all 16 Mach-O parts without changing compiled source bytes or
rights, and published a draft package. Core results: baseline 30 pass/2 fail,
native 37/1, optional 52/3. Paired no-debug control and native each passed 7/7.
The native mode's only failure is CDP revision `@000...000`; all behavior checks
passed. Remaining fullscreen failures require literal `normal` although the
runner was already maximized before entry and restored to maximized afterwards.
CSS fullscreen exit, binding snapshot clearing/retention, events and focus checks
were otherwise correct. This commit fixes both identified causes:

1. `ci/source_revision.py` authenticates the actual pinned upstream Git object,
   validates source/generator hashes, emits standard LASTCHANGE files, and
   records provenance. `ci/build.py` explicitly selects them via supported
   `use_dummy_lastchange=false`. Official/branding/compiler pins stay unchanged.
   Do not overwrite LASTCHANGE.dummy, generated C++ headers or expected CDP PIN.
2. Fullscreen exit accepts only `normal` or `maximized` on the exact expected
   window. Fullscreen/minimized/unknown/wrong-window results still fail; all
   CSS, snapshot, event and real-focus assertions remain.

That Mac package is **not a verified delivery**. Its draft is 431940255,
tag `build-156.0.8078.80-mac-arm64-c9ac6366f39a-706479414249`, ZIP asset
703093920, 252,684,636 bytes, SHA-256
`5d3e2f23fca62e07c4d2ea26e69ce467ffd8ddc3d0ea8dab82b36b9ed2392252`.
Its five published checksum entries and server digests were checked.

Mac run 41515581981 is now terminal, with a complete checkpoint in draft
431940572, tag `checkpoint-mac-arm64-c9ac6366f39a2bdd17c3-41515581981-1`.
Ready asset 703165989 has SHA-256
`00c430daf2ecfbda592033547b82fa3f395a36755f1628e014a891ecdd890463`;
six parts total 9,900,445,822 bytes, all server sizes/digests verified.
State is build-ready/complete, source `706479414249`, native16 Mac fingerprint.
Do not use partial drafts. The older complete fallback is draft 431878746,
ready asset 702999464, ready SHA-256
`530781afd71ec2711e0164dff62594c696f01d45dc2893816cb85ce4cb2f03ad`,
six parts totaling 9,900,397,712 bytes, source `b3237eac7f70`, build-ready/complete.
Prefer the newer complete exact-fingerprint cache.

The revision/fullscreen correction was committed and pushed as
`e146fe41bca31d079f7af03e1f1c7a28a1e57863`, with immutable
`ci-source-e146fe41bca3` and both corresponding final package tags. Mac retry
**41524595935** was dispatched at 21:01:59 UTC and is already running. Do not
dispatch a duplicate Mac build. Its eventual successful package source is the
e146 tag, even if later documentation-only commits exist on main.

Windows run **41503529408**, source `ci-source-81735e8f2ce2`, was still compiling
at 20:56 UTC, since 19:13:47 UTC. Mandatory clean exact Python, default GN-desc,
RC preflight and the 75,790-leaf/zero-missing input audit passed. Do not cancel a
live compile or checkpoint. Its configured pending-stage continuations are
remote and independent of the laptop, but retain their old immutable source.
Switch to the new metadata fix only after a terminal stage and complete cache;
avoid racing an existing automatic continuation with a second queued job.

## Next actions

1. Deliver/use the verified installers, checksums and instructions above; no new
   native build or file:// support change is requested.
2. Preserve healthy Windows checkpoint backup 41657571863. If continuing archival
   supervision, wait for its terminal result/ready marker, then verify manifest
   bytes, exact source/native identity and all server part sizes/digests.
3. A backup failure is separate from the already-verified installer. Diagnose
   its exact storage/transport failure and preserve the preceding complete cache;
   do not restart compilation blindly or use paid/external infrastructure.
4. Future native/version changes require immutable source/final tags, exact cache
   identity, fresh delivered-app behavior/normal Store checks and real UI review.
   Never retarget an existing source tag or overwrite original evidence.

## Hosted takeover observations

At 02:46 IST on November 3 (21:16 UTC on November 2), actual job APIs showed
Mac 41524595935 restoring its checkpoint and Windows 41503529408 compiling.
Neither job was cancelled or duplicated. This runtime can read Actions and
download authenticated draft assets through the existing GitHub integration;
no credentials were copied. The administrative Actions-permissions endpoint
returns 403; it does not block the required operations. The actual
`release-auth-probe.yml` dispatch, run **41527296038**, passed: standard hosted
Ubuntu created a tiny draft at the pre-existing `ci-auth-probe-67dea4dbe7e2`,
uploaded/downloaded and hash-verified its asset, then deleted the temporary
draft while preserving that tag. Its workflow commit is `ce666c2c524b` and the
asset SHA-256 is
`82a67a4de74c3f53f271d7b616ed1ace78bfa878d289b03666e75d87ac75db88`.
This establishes actual dispatch and hosted-publisher access, not a browser.

The Mac ready-manifest bytes independently match
`00c430daf2ecfbda592033547b82fa3f395a36755f1628e014a891ecdd890463`.
Its build-ready/complete state and native16 identity match the handover. Six
Windows preparation/input-diagnostic assets independently match their server
sizes/digests and all four published checksum entries: preparation complete,
no diagnostic events, 75,790 declared leaves checked, zero missing, no audit
errors. These are checkpoint/preparation observations, not finished binaries.

Local continuation checks: 140 Python tests ran with 15 skips (platform,
Ninja and selected-source fixtures unavailable); Node reported 67 passes and
one Windows-only skip. No browser runtime result is inferred. Installation
procedures are drafted in DISTRIBUTION.md and remain explicitly gated on actual
fresh-delivery evidence. Continue monitoring the existing jobs, then inspect
real compiler/package/test output before the next dependent action.

At 02:53 IST (21:23 UTC November 2), Mac preparation and its declared-input
audit had passed and incremental compilation was active since 21:21:50 UTC.
Windows compilation remained active. Mac's current 270-minute absolute budget
stops compilation around 07:02 IST November 3; Windows retains its immutable
220-minute budget and stops around 03:56 IST. The respective six-hour runner
limits are approximately 08:32 and 06:15 IST. Saves have a 120-minute step cap,
but must finish within the remaining job limit; the observed maximum complete
save is approximately 32 minutes. A disk guard also stops below 8 GiB free.
These are stage/checkpoint limits, not completion estimates. Both pending
campaigns resume only after successful complete saves; do not cancel them.
