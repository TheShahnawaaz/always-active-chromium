# Progress ledger

## Current state — 2026-11-01 23:00 UTC

There is no finished custom browser package yet. The current implementation is
the exact-source **15-file** patch at `6cea97a`, on Chromium `156.0.8078.80`.
It includes detached-document safety and the optional fullscreen tab-switch
ordering fix. Application/reversal/digest checks pass; actual native C++ and
runtime verification remain pending. Ordinary extensions and Web Store support
are retained in the design and source; normal Store installation/update checks
have not yet passed on a custom binary.

| Target | Authoritative hosted state | Next action |
| --- | --- | --- |
| macOS arm64 | [Run 41353967689](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41353967689), immutable source `67dea4dbe7e2`: source/toolchain/native14/GN preparation passed; Ninja compilation started at 22:05:43 UTC and the job has now entered checkpoint saving. The compiler outcome is not established by that step alone. | Let the existing stage finish saving, inspect its compiler logs/state, then migrate the exact native source changes and rebuild affected outputs. |
| Windows x64 | [Run 41355069621](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41355069621), immutable source `f2f4e1335f61`: complete source extraction, dependency hydration, self-tests and native14 application passed. GN could not execute the extensionless `bin/python3` path, although `bin/python3.exe --version` passed. A complete source/tool checkpoint was saved. | Correct the Windows GN interpreter invocation, migrate the checkpoint to native15 and run GN/Ninja. |

The complete Windows draft checkpoint is
`checkpoint-win-x64-1e3461dc246407d5a3bc-41355069621-1`: five SHA-256 checked
chunks totaling **7,667,423,246 bytes**, with `ready.json` uploaded last at
22:49:47 UTC. Its state is explicitly `source-ready/bootstrap-incomplete`; it
contains no completed browser or compiled C++ objects.

Both seed campaigns predate the detached-document fix. Their undelivered final
release tags were removed after checking that no corresponding release existed,
so they cannot publish an obsolete browser. Source refs and draft compiler
checkpoints are preserved. Migration is opt-in, allows only these two exact
seed commits with identical build pins, validates original/patched source
hashes, preserves unchanged outputs/timestamps, and requires a fresh real build.

Local CI tests currently pass: 29 tests, including bounded no-debugger cleanup, real Ninja
incremental reuse and the real selected-file native14-to-native15 transition;
the Windows-only extraction integration is skipped locally and has passed on
the hosted Windows image. These tests establish CI mechanics, not native
browser behavior. The passive no-debugger control passed 7/7 on original CFT,
and its native expectation correctly rejected that unmodified browser. Actual
native paired checks remain required on both packages. A temporary hosted
final-release authorization probe
[41355439888](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41355439888)
also passed create/upload/download/hash/delete using only the workflow token
and an exact pre-created source tag; it did not publish a browser.

The first native15 Windows migration dispatch,
[41360489459](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41360489459),
stopped before source restoration: two POSIX cleanup unit tests tried to mock
`os.killpg`, which does not exist on Windows. Those two tests are now explicitly
POSIX-only; two Windows process-tree cleanup cases exercise bounded taskkill
and failure reporting on every host. Production cleanup code is unchanged.
The retained source checkpoint is unaffected; the corrected 29-test suite
passes locally and still needs its next hosted Windows execution.

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
