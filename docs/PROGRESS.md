# Progress ledger

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
  uses immutable project source `2015fd2a2eeb`. Mac passed runner preparation and
  is preparing source/tools/GN. Windows stopped before large downloads because
  Git checkout CRLF conversion changed fingerprint bytes. Commit `9ffdca6`
  enforces LF across platforms; Windows needs a new tagged run with this fix.
- Windows extraction probe
  [41353041394](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41353041394)
  compares native and Git GNU tar with small explicit fixtures before choosing
  a fix for the earlier source extraction failure. No extraction errors are
  being ignored and no full source is fetched locally.

## Work in progress

- First hosted compilation and native behavior verification of the written patch.
- Actual Mac source/toolchain/GN results, then resumable compilation.
- Windows extraction diagnosis and a fresh tagged Windows build after LF/input
  handling is fixed.
- Toolchain hydration and resource-aware runner preparation.

## Not yet established

- Whether the constrained hosted runners can finish both full builds with the
  available disk, memory, time and free storage allowances.
- Whether every optional extension behavior has a useful native equivalent.
- Browser binary artifacts, native behavior test results, extension compatibility
  results, signing and distribution results.

Do not mark the goal complete from source changes or successful preflight alone.
