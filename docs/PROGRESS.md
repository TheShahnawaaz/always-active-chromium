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
  and approximately 16 GiB RAM, with Visual Studio 2026 version 18.11.1 and
  Windows SDK 26100. Windows disk capacity needs a corrected diagnostic print.
- Official Chromium source archive for the exact version is available and
  measures 4,422,962,028 bytes compressed; a full local Git clone is unnecessary.
- Full source/build outputs are not being downloaded onto the local Mac.
- Extension source and REA evidence from the initial investigation are retained
  locally, outside the public repository. The binary implementation and
  behavioral verification are still pending.

## Work in progress

- Exact-version native patch design and implementation.
- Source/resource-aware resumable GitHub-hosted build pipeline.
- Extension runtime oracle, behavioral feature matrix, and regression harness.
- Inspection of actual runner capacity/toolchains from the preflight logs.

## Not yet established

- Whether the constrained hosted runners can finish both full builds with the
  available disk, memory, time and free storage allowances.
- Whether every optional extension behavior has a useful native equivalent.
- Browser binary artifacts, native behavior test results, extension compatibility
  results, signing and distribution results.

Do not mark the goal complete from source changes or successful preflight alone.
