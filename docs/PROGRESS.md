# Progress ledger

## Current state — 2026-11-02

There is no finished custom browser package yet. The current implementation is
the exact-source **15-file** patch at `6cea97a`, on Chromium `156.0.8078.80`.
It includes detached-document safety and the optional fullscreen tab-switch
ordering fix. Application/reversal/digest checks pass; actual native C++ and
runtime verification remain pending. Ordinary extensions and Web Store support
are retained in the design and source; normal Store installation/update checks
have not yet passed on a custom binary.

| Target | Authoritative hosted state | Next action |
| --- | --- | --- |
| macOS arm64 | [Run 41363256213](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41363256213), immutable source `9f6d9a79aef2`: restored the prior compiler checkpoint, migrated native14 to native15, validated Dawn's exact Go toolchain and generated GN successfully. Ninja compilation began at 23:57:56 UTC on November 1 and remains in progress. | Preserve the live build and its retained objects; inspect its actual terminal result. |
| Windows x64 | [Run 41365869868](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41365869868), immutable source `0963bca534ac`: restored the native15 checkpoint and passed exact Go/gperf tool and GN checks. Ninja rejected the next missing host input, `buildtools/win-format/clang-format.exe`, before C++ actions. The complete native15 checkpoint has been saved. | Hydrate the exact upstream formatter pin, then run the new declared-input audit before compilation. |

The earlier Mac run
[41353967689](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41353967689)
completed **10,753 of 57,570 Ninja actions** before a missing nested Dawn Go
executable stopped its source generator. Its five-chunk checkpoint totals
**7,566,257,986 bytes**. The current Mac campaign restored that checkpoint,
applied the approved native15 migration, hydrated Dawn's exact
`version:3@1.26.6` host package, and passed its absolute executable version/host
check. This proves resumed preparation, not a completed browser.

The earlier Windows native15 run
[41360825174](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41360825174)
passed preparation but Ninja rejected a missing `third_party/gperf/bin/gperf.exe`
before executing C++ build actions. Its complete five-chunk checkpoint totals
**7,705,525,026 bytes**. The current campaign restores it and hydrates the exact
upstream gperf Git revision, executable, README and license with fixed hashes.
Those checks passed on the hosted Windows runner at 00:37:15 UTC. The latest
run then rejected the missing `buildtools/win-format/clang-format.exe`, needed by
Crubit's generated Rust/C++ support header. Its complete five-chunk native15
checkpoint totals **7,773,142,945 bytes**. The next retry will include an exact
formatter repair and the read-only declared-input audit, which reports missing
leaves together before any compile attempt.

Both original seed campaigns predate the detached-document fix. Their undelivered
final release tags were removed after verifying that no corresponding release
existed, so they cannot publish an obsolete browser. Source refs and draft
compiler checkpoints remain available. Migration is opt-in, allows only the two
exact approved seed commits with identical build pins, validates original and
patched source hashes, preserves unchanged outputs/timestamps, and requires a
fresh real build. CI-only tool repairs leave the native fingerprints unchanged.

Local CI tests currently pass: **45 tests**, including exact nested-Go, gperf and formatter
selection/rejection, bounded no-debugger cleanup, real Ninja incremental reuse,
the selected-file native14-to-native15 transition, and the read-only declared
input audit against the pinned Ninja. The Windows-only GNU tar
integration is skipped locally and has passed on the hosted Windows image.
These tests establish CI mechanics, not native browser behavior. The passive
no-debugger control passed 7/7 on original CFT, and its native expectation
correctly rejected that unmodified browser. Actual native paired checks remain
required on both packages. Hosted final-release authorization probe
[41355439888](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41355439888)
also passed draft creation, upload, download, hash verification and deletion
using the workflow token and an exact pre-created source tag; it published no
browser.

Hosted normal Store prerequisite inspection
[41362212167](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41362212167)
passed both platforms: six finite capture checks per OS, actual HTTP 200 listing,
**enabled** Add-to-Chrome DOM/AX buttons, and owned visible native window access.
All report/provenance/status/checksum asset hashes were independently verified.
A later normal Add click and unaccepted permission-dialog inspection
[41365872867](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41365872867)
passed **11/11 on Windows**: the real owned native dialog named the audited
extension, showed enabled Add extension/Cancel controls and its all-websites
permission text. Normal browser close cancelled the prompt; the extension
remained absent from the persisted registry.

The Mac-only dialog inspection
[41370550957](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41370550957)
subsequently passed **11/11**. The earlier capture stopped at depth eight before
reaching the native sheet's permission text. The observer now applies a deeper
bound only inside a verified owned native sheet, retaining its node, time,
output and ownership limits. The actual AXSheet contains the exact target
heading, enabled Add extension/Cancel controls, and its all-websites permission
text. All four release assets and their checksum manifest were verified; normal
browser close cancelled the unaccepted prompt and persisted target absence
passed. No permission was accepted or extension installed in any of these
Store trials. Actual Store installation, execution, restart, update and removal
checks still remain on both custom packages. The separate
[Store compatibility plan](../tests/STORE-COMPATIBILITY-PLAN.md) covers a second
supported MV3 extension, uBlock Origin Lite, with update-check and genuine
version-transition evidence kept distinct.

An earlier local disabled Store button did not establish a general compatibility
failure: a local brand-only counterfactual did not enable it, hosted reference
browsers showed an enabled button on both OSes, and a later fresh local reference
also showed it enabled. No production user-agent/branding patch is justified by
those observations.

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
