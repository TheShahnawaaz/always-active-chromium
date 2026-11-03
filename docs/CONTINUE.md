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

**Active final Windows CI replay: [41657571863](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41657571863),
source `ci-source-07fb6c3f9ed7`.** Full source/workflow commit:
`07fb6c3f9ed75340048ae6aeb0df5696c5b59fde`. Both matching final build tags are
pushed and independently resolved to that commit. Exactly one dispatch was
admitted **14:49:55 UTC / 20:19 IST**, after the old run was terminal and the
completed checkpoint verified. Inputs: win-x64, bootstrap false, migrate false,
auto-resume true, stage 0/max 48. Preserve this replay; do not duplicate it or
rebuild Mac. It validates the normal installed-app core target from cached outputs.
Latest package bytes/provenance and hosted core/fresh-delivery results still
need inspection before closeout. The already-verified Windows installer below
remains available and unchanged while this CI correction is validated.

**Both actual development packages have passed fresh delivery and UI review.**
Mac remains the unchanged e146 package below. Windows source
`ci-source-dd4dfe7709ce` passed real default per-user installation, baseline
**32/32**, native **38/38**, optional **55/55**, paired no-debug control/native
**7/7 each**, and all **20/20** normal uBlock Origin Lite Store phases in
[41654101196](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41654101196).
Controller: `03dc3d717e0cac1035e00f8bf717687513dce36d`. All seven finite delivery
assets and six checksum entries were independently downloaded/hash verified.
The actual **1044×788** installed-browser PNG was visually inspected: full
standard Chromium controls and rendered fixture, with no added always-active
controls/banners. Original automated review fields remain unchanged; see
`docs/releases/win-x64/`, `docs/UI-REVIEW.md` and the separate visual review.

Windows installer draft **432796940**, tag
`build-156.0.8078.80-win-x64-cfc3210920f1-dd4dfe7709ce`, has six independently
hash-verified build assets/five checksum entries. Installer asset **705879122**
is **215,424,512 bytes**, SHA-256
`4e0ae88f4b45b1ea5e6c1725320fb5a851a25c63e42c299889dee2963aba0ad3`.
Installed x64 executable: **4,200,448 bytes**, SHA-256
`a622201cb3501ea22b2851878f144c2a70270bccc58cef333f8bcfa6727030b4`.
Delivery draft **432809252** contains the verified evidence and PNG, asset
**705910479**, SHA-256
`dd4178db02d8dbb4f4961fc5be7fe42cabf2c675e21f7624c1a30f1b7e30c343`.
Store `no_update` is not a genuine newer-version upgrade. Persisted registration
absence is verified; absence of every removed-extension identifier is not claimed.

**One CI layout correction remains to validate before final closeout.** Original
build [41638453497](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41638453497)
compiled at 14:21:41 UTC and packaged at 14:21:50: actual complete/exit 0, no
compiler events, all finite diagnostics verified. Its core checks against the
uninstalled `D:\aacc\src\out\AlwaysActive\chrome.exe` failed at startup:
Chromium's AppContainer `AccessCheck` cannot read/execute that build-tree file,
error 0x5, followed by a sandbox policy fatal check. The actual published
`workflow_test_outcome` is failure despite the REST effective step success under
`continue-on-error`. Do not relabel that build-tree failure. The unchanged
normal installer passed every fresh test with the sandbox and flags unchanged.

The committed/pushed correction adds `ci/install_build.py` and a Windows-only workflow
step to install the actual task-owned mini-installer before core checks, using
the same already-proven clean-identity/per-user/x64/version guards as delivery.
It binds source/workflow/manifest, unchanged installer bytes and installed exe
hash, records installation provenance in the build manifest, and selects that
executable for the unchanged tests. It refuses existing Chromium and preserves
stock Google Chrome. No ACL, sandbox, native source, compiler pin or fingerprint
is changed. **148 local Python tests pass (15 platform/tool/source skips)**,
including four new host/provenance/mutation guards; workflow YAML parses.

The completed output cache is draft **432797322**, tag
`checkpoint-win-x64-cfc3210920f1d83aa4ac-41638453497-1`, six parts totaling
**10,669,016,313 bytes**. Downloaded ready asset **705955160** is **6,192 bytes**,
SHA-256 `316cedd7a10bd83ab5d88ed3ae79fd247feb7f025243b942e42e9e179fcf6f5a`.
Its bytes, source dd4dfe, native16 fingerprint/version/revision, build-ready/
complete state, authenticated revision metadata and every part's server size/
digest were verified. Save completed **14:47:39 UTC** in **24m56s**. The old job
ended **failure at 14:47:46 UTC** because of the real uninstalled-layout core
failure; automatic continuation was skipped for completed compilation. Final
Ninja counter was **3,243/3,243**, including the real mini-installer link.
All native outputs are retained; no cold rebuild or tag retarget is authorized.
The corrected immutable source/replay above now reuses this verified cache.

Earlier stages and the positive WebAuthn repair proof are retained in
PROGRESS.md. Standard-hosted independent audit 41638507119 and its finite receipt
`docs/evidence/windows-41598060999-audit.json` verified the preceding pending
checkpoint (8,849,247,927 bytes). It is superseded when this complete cache is
ready; normal cleanup may remove older same-configuration drafts.

**Coordinator execution was restored at 13:03 UTC / 18:33 IST.** A new workspace
message arrived, `pwd` succeeded, and the clean local checkout fast-forwarded to
main `638fe1f`. The reconnection request is resolved; no answer or new approval
is needed. Between 11:13 and 13:03 UTC the executor reported unavailable while
the provider reported running/connected with no failure/retained diagnostics.
Its underlying cause was not exposed. No credential or network-policy change
was made, and healthy GitHub jobs were never restarted or cancelled.

The bounded read-only audit filled that gap through
`.github/workflows/audit-current-windows-stage.yml` on standard `ubuntu-latest`,
using the repository's own scoped job token. Its receipt above is actual small
asset download/hash evidence, not browser runtime proof. This historical audit
is pinned to stage 1 and is useful only while that cache exists; do not rerun a
retired checkpoint or confuse its failure with a browser failure. Direct CLI
and the existing final-delivery workflow can now be used normally.

**Mac is delivered as a verified development package; Windows remains active.**
Final Mac delivery **41533441385**, controller `68a55d8132e9`, passed real
extraction, all four behavior modes and 20/20 normal Store phases. Its actual
1000×677 normal-window PNG was visually inspected: complete standard Chromium
toolbar/tab strip/profile/menu and rendered fixture, with no added always-active
controls or banners. All seven evidence assets and six manifest entries match
their server sizes/digests and downloaded hashes. See `docs/UI-REVIEW.md` and
`docs/releases/mac-arm64/` for the separate review, verification and installation
records. Screenshot SHA-256:
`540fbca5d806231a06c3a759f8b8b60a6fd5b6a5caf89e8da0a12b142c1f6f52`.
The original automated review fields were preserved; the later visual review is
separate evidence, not an alteration of CI results.

Mac package draft 431995111 has its verified download/checksum assets and updated
installation/review notes at
https://github.com/TheShahnawaaz/always-active-chromium/releases/tag/untagged-4eebb053bab880d711db
All six original asset IDs, sizes and digests remain unchanged; its original
five-entry manifest is still valid. Extra document uploads from the coordinator
were rejected at `uploads.github.com` by the runtime's network policy. No asset
was changed by those failed uploads. The permitted API path successfully updated
draft notes, while instructions/review records and the exact screenshot are
committed to the repository. Do not bypass the network policy or move credentials.
The client projectless `/codex/.../output` path also cannot be created by this
runtime's non-root user; use the existing GitHub release/repository route, not
broken local output links. No permission request is needed for this fallback.

Latest Mac progress: **run 41524595935** at `ci-source-e146fe41bca3` compiled
successfully, sealed all 16 Mach-O parts with compiler outputs unchanged, and
passed core baseline **32/32**, native **38/38**, optional **55/55**, paired
no-debug control/native **7/7 each**. The correct pinned upstream revision is
reported. Its complete draft is **431995111**, tag
`build-156.0.8078.80-mac-arm64-c9ac6366f39a-e146fe41bca3`.
ZIP asset **703257988** is **252,685,495 bytes**, SHA-256
`7dbfafec37054e029848f1cedff431244b3031f96ae2cc6b076305119986d2b8`.
All six downloaded assets match server sizes/digests and all five manifest
entries. The entire build run is now green. Its incremental rebuild completed
**271/271 actions**, then saved a complete six-part **9,901,553,400-byte**
checkpoint in draft **431995372**, tag
`checkpoint-mac-arm64-c9ac6366f39a2bdd17c3-41524595935-1`.
Ready asset **703318165** is 5,942 bytes, SHA-256
`8da87fdafdc63eb430ddaa65fbe89ff2ab3687e6514b1a5fdef574ca515d7e83`.
Its bytes, source/native/revision identity and all server part digests/sizes
were verified. This newest complete e146 cache supersedes the older caches;
normal checkpoint cleanup may have removed earlier drafts.

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

1. Inspect actual live runs and queued jobs before dispatching anything.
   Preserve final CI replay 41657571863 at source ci-source-07fb6c3f9ed7.
   Its prior completed cache is already verified; do not duplicate or cold build.
2. Use the latest committed fix with a matching immutable `ci-source-<HEAD12>`
   tag and both `build.final_release_tag(platform, HEAD)` tags. Never retarget
   an existing tag. Push commits/tags before dispatch. Keep `migrate_native=false`
   for exact native16 caches, `bootstrap_only=false`, `auto_resume=true`.
3. Mac metadata rebuild, fresh-delivery/Store verification and native UI review
   are complete. Its source is still e146 and its original ZIP is unchanged.
   Do not dispatch another Mac compile or verifier without a new concrete issue.
4. Finish Windows through standard hosted stages. Read real failure diagnostics
   and preserve completed checkpoints; no blind repeated reference trials.
5. For each real package with passing core tests, dispatch
   `verify-delivery.yml` with its exact source tag and one platform. Verify the
   fresh extracted/installed executable in all four modes, normal Web Store
   installation/execution/restart/update-check/removal, hashes and cleanup.
   Reference Chrome/fixture results are not native delivery evidence.
6. Review actual native UI captures/manual evidence for both targets, then
   complete installation/limitations docs. Document Chromium branding,
   restricted Google services, ad-hoc/unsigned distribution and manual updates.
   A genuine future extension version upgrade remains separate from `no_update`.

The cloud handoff itself is complete only when a published environment and a
real independent hosted coding task are visibly running. GitHub build jobs
already survive laptop shutdown; a local Codex conversation does not.

The user reported the environment published and then chose to hand the goal
to Dot. Verify the selected environment and GitHub API access in Dot's actual
runtime; the onboarding's earlier Forbidden responses predate the API-domain
configuration. Main also contains documentation-only commit `0fc07ef` after
the immutable e146 build source; preserve later work.

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
