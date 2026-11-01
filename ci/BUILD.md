# GitHub-hosted build route

The workflow is executable build infrastructure, **not evidence of an existing
browser binary**. Both actual target builds, their native behavior tests, and
interactive Chrome Web Store checks must finish before claiming completion.

## Source and native patch

`pins.json` fixes Chromium **156.0.8078.80**, upstream commit
`fb096c0011f9d50f0a264a9376420cdea9c421e3`. It uses the official
[4,422,962,028-byte source archive](https://commondatastorage.googleapis.com/chromium-browser-official/chromium-156.0.8078.80.tar.xz)
and its [published SHA-256](https://commondatastorage.googleapis.com/chromium-browser-official/chromium-156.0.8078.80.tar.xz.hashes),
`5b1a1f3bfdf4fc559db4eddfb4492b72ffcec7ae1a52b30f8b172230788f5740`.
This avoids a full source Git history and its disk overhead.

The archive contains the source dependencies. `build.py` hydrates the selected
host Clang, Rust/libclang, GN's CPython interpreter, Ninja, Node, TypeScript and DevTools build
dependencies using the **archive's own pinned DEPS**, not moving upstream main.
It also hydrates Windows WTL/WebView2/7z, Mac ANGLE Metal libraries, and the
subresource-filter ruleset data. Dawn's source generator uses its own nested
[DEPS-pinned Go 1.26.6](https://dawn.googlesource.com/dawn/+/8114a24a35eed1db88d1d897e8bd193a8c334712/DEPS):
the host Mac arm64 or Windows amd64 CIPD package is SHA-256 checked against
the immutable ZIP digest in `build.py`, then its absolute executable must report
the expected version and host. It never substitutes a system Go installation.
Host Mac Swift comes from the selected Xcode;
the hermetic Swift package is an iOS requirement.
GCS downloads are SHA-256/size checked against DEPS. GN/Ninja CIPD zip hashes are
also fixed in `pins.json`; other CIPD build packages use their DEPS version and
record the downloaded hash in `dependencies.json` in the checkpoint. GCS archive
versions use the exact DEPS object generation. No ungoogled feature-removal
patches or flags are used.

Before GN, the native applicator runs `--check`, applies idempotently, then runs
`--verify-applied`. Its exact source and output hashes reject another version or
an unexpected edit. Source/patch/configuration fingerprints isolate checkpoints;
documentation and authoring caches are excluded from that fingerprint.
Each resumed prepare checks hydration again: per-dependency plan markers skip
unchanged packages and preserve their mtimes, while newly selected tools are
hydrated. `hydration_revision` in the pins versions the hydration semantics.
After complete archive extraction and the native source/version check, a
`source-ready` / `bootstrap-incomplete` state can be checkpointed even if a
later tool download or GN generation fails. That failed run still skips
compilation and automatic continuation. A corrected retry rehydrates any
incomplete dependencies, rechecks the patch, and regenerates GN. An interrupted
or unvalidated source extraction is never declared checkpointable.

## Measured runners and build choices

Successful public-repository preflights: runs
[41348658261](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41348658261)
and [41349098782](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41349098782).

| Target | Standard runner | Measured resources | Fixed build root |
| --- | --- | --- | --- |
| macOS arm64 | `macos-26` | 3 CPU, 7 GiB RAM, approximately 96 GiB initially free | `/Users/runner/aacc` |
| Windows x64 | `windows-2025-vs2026` | 4 CPU, 16 GiB RAM, approximately 220 GiB free on D: | `D:\aacc` |

The Mac cleanup inventories and removes only real, nonselected
`/Applications/Xcode_*.app` bundles on the ephemeral hosted runner. It preserves
the selected Xcode and all of its SDKs. APFS cloning means advertised bundle
sizes are not guaranteed reclaimed bytes; free space is measured again. No
arbitrary home/workspace deletion or simulator/SDK pruning is performed.
The runner compiles and links a tiny Metal shader. If Xcode's optional Metal
component is missing, it obtains it with Apple's public
`xcodebuild -downloadComponent MetalToolchain` and repeats the functional probe.
The build processes raise their open-file limit to 10,240 (or the hard limit).

Windows retains the provisioned VS 2026 toolchain. Its initial SDK was 26100, so
the workflow installs SDK 28000 from Microsoft's fixed download URL, verifies
the installer's Microsoft Authenticode signature, and requires the 28000 include
directory. Chromium's pinned Windows build requirements call for SDK
10.0.28000.2270 (include-directory name `10.0.28000.0`). No SDK installer or tool
payload is downloaded onto the user's Mac.

The official source archive uses Git for Windows' bundled **GNU tar 1.35** with
a UTF-8 locale, `--force-local`, and strict native symlinks. The source archive's
SHA is verified before extraction and any extractor failure remains fatal.
This choice is backed by hosted
[probe run 41353041394](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41353041394):
Windows system bsdtar 3.8.9 failed valid CJK/emoji PAX filenames with the exact
"empty or unreadable filename" error seen in the real source extraction. Setting
its UTF-8 locale did not help. Git GNU tar preserved those Unicode names, a
403-character path, native relative symlinks and hardlinks. No global tar exit
code is ignored. Both tools normalize some raw-byte/NTFS-special names; that
diagnostic limitation is recorded, not presented as exact support for every
Linux test filename. Host tool archives retain their existing extraction path;
the change is limited to the Windows source archive. The selected extractor and
version are recorded in build-state provenance.
The hosted CI checks invoke this exact source-unpack helper on a tiny Unicode
`.tar.xz` before the large download. GNU tar manages its compression provider;
no unverified assumption about the location of a separate `xz.exe` is imposed.
Windows GN explicitly selects the hydrated `bin/python3.exe` using its official
`--script-executable` switch. The pinned GN's own help documents this override;
a small local GN fixture confirmed it takes precedence over an unusable dotfile
interpreter and is preserved in Ninja's regeneration command. This fixes the
measured Windows interpreter-launch failure without editing upstream `.gn` or
changing compiler arguments.

Release-optimized, noncomponent Chromium is built without PGO, ThinLTO, or debug
symbols. This reduces memory, disk and build time; it sacrifices some official
Chrome performance and crash-debugging detail. Mac uses Apple's supported linker
(`use_lld=false`), two compilation jobs, no dSYMs, and one link at a time.
Windows uses three compilation jobs and one link at a time. The standard
extension platform, Web Store integration, sandbox, UI and upstream security
defaults are retained. No paid runner or external compute fallback exists.

Seven GiB on Mac remains a material uncertainty. Upstream's no-dSYM Mac linker
heuristic budgets roughly 4 GiB per link, but only an actual full build can
establish that this version links on this runner. An OOM or exhausted disk is a
measured blocker, not a reason to silently use a paid provider.

## Resumable stages and storage

Choose **Build native Chromium** in Actions. For the first source/toolchain/GN
check, set `bootstrap_only=true` and `auto_resume=false`. That saves a reusable
source checkpoint. Start it again with `bootstrap_only=false` to compile.
Matching checkpoints are found automatically. `build_ref` optionally fixes the
small project repository to an immutable source tag; a blank field uses the
workflow commit. **Before dispatch**, create `ci-source-<first12-of-commit>` at
the chosen project commit using the already authorized repository credential.
The workflow checks that exact immutable tag against `git rev-parse HEAD` before
large downloads. Continue stages retain the source tag, even if `main` advances.
Package provenance records the resolved checkout SHA, not the moving workflow
definition's `GITHUB_SHA`.

Source tags record provenance. They are **not sufficient authorization** for
creating a different release tag at that older commit. GitHub
[enforces workflow permissions for releases targeting unreferenced workflow-changing commits](https://github.blog/changelog/2023-11-02-github-actions-enforcing-workflow-scope-when-creating-a-release/).
The repository's observed test publishers still received 403 when a different
source tag existed. Do not work around that guard with a PAT secret or broader
permissions. Checkpoints use the default branch solely as a clearly labeled
storage anchor; the manifest, not that storage tag, identifies the actual code.

Before **compilation** dispatch, also precreate each exact final binary tag at
the same project commit. Its name is
`build-<Chromium-version>-<platform>-<native-fingerprint12>-<checkout-commit12>`.
To print it, run `python ci/build.py source-ref --platform mac-arm64` (and
`win-x64`) after creating the source tag. The nonbootstrap workflow requires
that tag before downloading/building; the publisher checks its resolved SHA and
uses `gh release create --verify-tag` with no `--target`, so a final binary release
cannot silently point at the checkpoint storage anchor or another project commit.

For example, in the small project repository (never a Chromium checkout):

```sh
aacc_commit="$(git rev-parse HEAD)"
aacc_source_tag="ci-source-${aacc_commit:0:12}"
git tag "$aacc_source_tag" "$aacc_commit"
git push origin "refs/tags/$aacc_source_tag"
gh workflow run build.yml --ref main -f build_ref="$aacc_source_tag" -f platform=both -f bootstrap_only=true -f auto_resume=false
```

Each job has GitHub's six-hour limit. Compilation stops at **220 minutes from
the initial budget step**, with a graceful interrupt and a forced termination
fallback. Completed Ninja objects and dependency databases survive. SDK setup,
restoration and source preparation consume that same budget. A disk monitor
stops compilation below 8 GiB free and reports a failure rather than dispatching
an endless chain with the same capacity problem.

Saving uses a streamed, level-1 zstd/PAX archive. A single upload chunk on disk is
at most **1,800,000,000 bytes**; source and outputs are never duplicated into one
huge archive. File and directory timestamps are restored to exact nanoseconds,
because rounding object mtimes invalidates Ninja's dependency database. Chunks
are hashed, ordered, and authenticated. Restore rejects unsafe archive paths.
Downloads and uploads have explicit timeouts.
GN-generated `sdk/xcode_links` is excluded: it contains absolute links to the
runner's Xcode and is recreated by GN on each resumed runner. Safe archive
filtering remains enabled for the rest of the tree.

Checkpoints are **draft GitHub Release assets**, not Actions artifacts/caches or
Git LFS. [GitHub's release documentation](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases#storage-and-bandwidth-quotas)
permits up to 1,000 assets per release, each under 2 GiB, with no total release
size or bandwidth quota. This route does not buy extra Actions storage. Each
complete new generation uploads `ready.json` last and only then removes this
configuration's prior checkpoint drafts. A failed upload leaves the preceding
complete generation usable; incomplete drafts are skipped. Final browser draft
releases are separate and are never removed by checkpoint cleanup.

After a successful pending checkpoint, a bounded `workflow_dispatch` starts the
next job. GitHub explicitly permits this event to trigger workflows using
[`GITHUB_TOKEN`](https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-when-your-workflow-runs/triggering-a-workflow#triggering-a-workflow-from-a-workflow).
The token has repository `contents:write` for drafts and `actions:write` for
dispatch. No PAT, external account, cache service or signing secret is needed.
Job concurrency serializes each target. Automatic continuation defaults to 48
stages and can be disabled or bounded to 1–100; a stopped chain remains manually
resumable. A real compiler failure saves the checkpoint and stops the chain.

There is no measured completion-time promise. The current upstream
ungoogled-chromium Mac workflow uses a prohibited provider; its historical
GitHub-hosted design is useful evidence for staging, not proof that this build
will finish. Its [migration discussion](https://github.com/ungoogled-software/ungoogled-chromium-macos/pull/305)
reports a GitHub build running around three days without finishing. A long
sequence of successful resumable stages may therefore be required.

## Explicit native cache migration

Native runtime corrections do not justify silently accepting arbitrary older
source trees. `migrate_native` is **off by default**. When explicitly enabled,
restore still prefers an exact current-fingerprint checkpoint. Its only fallback
is the corresponding approved immutable seed: Mac
`ci-source-67dea4dbe7e2`, Windows `ci-source-f2f4e1335f61`. These seeds contain a
known native constructor defect and are compiler caches, never deliverable
browsers. Their undelivered final build tags are quarantined separately by the
repository owner; immutable source refs and seed checkpoints remain available.

Migration reads four small Git blobs at the seed state's exact repository
commit: pins, provenance, applicator and patch. It verifies the immutable ref,
recomputes the old fingerprint independently, requires identical PINS bytes,
checks the same platform/root/upstream/schema, and compares restored `args.gn`
to the exact current platform configuration. Old Python is never executed.
The current stdlib patch parser alone handles exact hunks and hashes.
One strict source-only case may omit GN arguments: the recorded phase/status
must be `source-ready`/`bootstrap-incomplete`, `out/AlwaysActive` must be entirely
absent, and the measured restored compiler-output timestamp must be zero.
An existing output tree without matching `args.gn` is always rejected.

The complete union is bounded to 64 existing `.cc`/`.h`/`.idl` files and 64 MiB
of source; GN, DEPS and toolchain edits are forbidden. All file types, paths,
input digests, reverse transformations and resulting digests are validated
before any write. Recognized upstream/old-patched partial states are supported;
foreign edits, changed configurations, unavailable metadata or unready seeds
fail closed. Opting into migration without a ready approved seed does not start
a surprise cold build.

Only changed source files are replaced. Unchanged bytes/mtimes, Ninja databases
and all compiled objects remain untouched. The restore tracks compiler-output
timestamps; changed source receives at least a 100 ms newer timestamp, verified
by `stat` after filesystem rounding. Unreasonable future output times are
rejected. Failed writes or native verification roll back changed sources and
never bless the new state. The remote seed is not modified by restoration.

After current `--verify-applied` passes, the state records both commits,
fingerprints, changed paths and timestamp evidence, and becomes
`source-ready`/`bootstrap-incomplete`. Ordinary preparation revalidates the
native source and regenerates GN. Only a successful real Ninja build can mark
the new state complete, package it, and run browser verification. New checkpoints
use the new fingerprint; seed drafts are retained. Focused tests cover rejection,
rollback, partial states, unchanged mtimes, the 100 ms margin and actual Ninja
selective rebuilds. The local selected-file test migrates the real 14-file seed
to the current manifest and verifies every current native source digest without
downloading or compiling full Chromium locally.

## Packages and verification

Mac packaging verifies the generated `.app` signature structure and makes a
`.zip` with the full app. Windows builds the real Chromium `mini_installer`
target and packages the resulting installer executable. These are development
packages: no Apple Developer ID/notarization or Windows Authenticode certificate
is configured. They keep Chromium's own identity/profile, separate from Google
Chrome. See `docs/DISTRIBUTION.md` for installation and product differences.

After compilation the workflow runs the repository's native behavior and MV3
extension harness against the real executable in three modes: master feature
disabled for the built-browser baseline, native defaults, and optional native
fullscreen/background-navigation flags. A required fourth variant runs paired
control/native website reports with normal CLI launches and no CDP, WebDriver,
extension or automation flag. Each variant has its own fixture profiles. The
first three have four-minute bounds; the paired zero-debugger run has three
minutes, with bounded process cleanup inside one 20-minute step. Results are
aggregated with their mode/flags and individual checks; uncovered behaviors stay
explicit. Only the zero-debugger `results.json` is collected; its profiles and
per-process browser logs are excluded.
On POSIX, an outer zero-debugger timeout first sends SIGTERM to its controller
and allows 30 seconds for its own verified cleanup of detached browser groups.
Only a still-hung controller is force-killed afterward. A timeout always fails
verification; late detached-process cleanup is explicitly marked uncertain in
the aggregate instead of being claimed successful.
It uploads only the package,
checksums, provenance, `results.json`, `browser.log`, and a test-status record to
a **draft** build release. Browser profiles, cookies, storage and extension
fixtures are excluded. A failed test fails the workflow and remains visible in
the draft's evidence; packaging alone does not mark the browser verified.
Headful window availability and actual Web Store installation still require
observed results on both hosted operating systems.

Small local checks (no Chromium fetch/build):

```sh
python -m pip install -r ci/requirements.txt
python -m unittest discover -s ci -p 'test_*.py' -v
actionlint .github/workflows/build.yml
```

The checkpoint tests cover chunk boundaries, corrupt data rejection, safe paths,
mode/symlink/content/nanosecond preservation, and (when Ninja is available) a real
dependency-database no-rebuild roundtrip.
