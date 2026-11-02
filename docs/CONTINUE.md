# Continue the browser delivery

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

At 20:56 UTC on November 2, Mac run 41515581981 was still saving its checkpoint
(started 20:33:22 UTC). Draft 431940572 had partial parts and no ready marker.
Do not use partial drafts. The older complete fallback is draft 431878746,
ready asset 702999464, ready SHA-256
`530781afd71ec2711e0164dff62594c696f01d45dc2893816cb85ce4cb2f03ad`,
six parts totaling 9,900,397,712 bytes, source `b3237eac7f70`, build-ready/complete.
Prefer the newer complete exact-fingerprint cache once its ready marker exists.

Windows run **41503529408**, source `ci-source-81735e8f2ce2`, was still compiling
at 20:56 UTC, since 19:13:47 UTC. Mandatory clean exact Python, default GN-desc,
RC preflight and the 75,790-leaf/zero-missing input audit passed. Do not cancel a
live compile or checkpoint. Its configured pending-stage continuations are
remote and independent of the laptop, but retain their old immutable source.
Switch to the new metadata fix only after a terminal stage and complete cache;
avoid racing an existing automatic continuation with a second queued job.

## Next actions

1. Inspect actual live runs and queued jobs before dispatching anything. New
   Mac work can queue behind the current save (`cancel-in-progress:false`);
   this completed compile cannot auto-dispatch a pending-stage continuation.
2. Use the latest committed fix with a matching immutable `ci-source-<HEAD12>`
   tag and both `build.final_release_tag(platform, HEAD)` tags. Never retarget
   an existing tag. Push commits/tags before dispatch. Keep `migrate_native=false`
   for exact native16 caches, `bootstrap_only=false`, `auto_resume=true`.
3. New Mac build should restore the newest complete cache, run prepare/GN,
   incrementally rebuild metadata consumers, repackage and rerun core tests.
   Do not cold-build or change compiler/native pins to repair metadata.
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
