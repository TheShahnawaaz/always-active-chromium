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
subresource-filter ruleset data. Host Mac Swift comes from the selected Xcode;
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
small project repository to a commit; a blank field uses the workflow commit.

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
fullscreen/background-navigation flags. Each mode has its own fixture profile
and a five-minute limit, inside one 20-minute step. Results are aggregated with
their mode/flags and individual checks; uncovered behaviors stay explicit.
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
