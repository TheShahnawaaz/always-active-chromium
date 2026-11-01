# Oracle evidence and remaining checks

This ledger separates exact packaged-source evidence, actual runtime
observations, and native-browser tests that still require a built binary. No
custom Chromium binary has been tested by this audit yet.

## Artifact identity and static REA evidence

| Item | Identity |
| --- | --- |
| Shipped extension | Always active Window - Always Visible 0.4.8, Web Store ID `ehllkhjndgnlokhomdlhgbineffifcbj` |
| CRX SHA-256 | `17e792706dcc8d7b1ad236bd090b662ca97786c085594b35da421851a33b655b` |
| Derived ZIP SHA-256 | `8eee6ad2b1fbc04726f77eb6eada38c700b91f13132cb64b8012cd9b7e7b038c` |
| REA extracted-tree identity | `1e756d9c930a703fe6cf74fe67f54ff3ad6491b3bf46a75ddaa851c7b7a7b7e4` |
| `main.js` SHA-256 | `8e0156ce545d5d6c7c724c2a134129c22619fc40ae306dcbc567cbd939ef1d13` |
| `isolated.js` SHA-256 | `b5147c3be4bb4911c7e2efbe47a13b055a54dbb3132057e9394ace94f564b51a` |

The CRX3 header was removed to produce the derived ZIP. The archive inventory
was complete (35 entries, 25 files, 10 directories, no integrity contradictions).
REA parsed six JavaScript files without parse failures. Its semantic graph was
partial with unknowns; direct packaged source and configuration were therefore
read for the audited behavior. None of the static evidence establishes that a
feature executed.

| Evidence | Scope |
| --- | --- |
| `ev_bae9e91a24ac07a8d6507799451d0888bad6e88f7a1dc5d27ebbfef248b17b95` | Archive inventory |
| `ev_35a6a6b40ae7644957100673bd4f6c950e22bf09df354ec56cbb11135041a3fc` | JavaScript application analysis |
| `ev_7da6d01a6df83d8236b8075eaac8ce02073780bf66cb561b7acd724a1afa0902` | Worker/module evidence |
| `ev_d617d3f71131444d78e989d27d7ec4391d657b92f9a5e59dad25646748606f8c` | MAIN-world injection evidence |
| `ev_36e7b0239c14de2d33b04628fa157d86527f0fdc10184883fccb11d522546776` | ISOLATED-world injection evidence |

The full initial bundle remains in the sibling investigation archive as
`rea-evidence-bundle.json`; its absolute machine path is intentionally not
published here.

## Controlled runtime environment

The audit acquired the official Chrome for Testing **156.0.8078.80 mac-arm64**
ZIP from Google's public Chrome-for-Testing storage. ZIP SHA-256:
`8bc590d1b1acac042a000234c768f31830f25a3983a83ed5e067114c87c4cad1`.
The executable SHA-256 was `c6279ef2230d17c6007ea1dc5342b67b0e6b0860741392de8eb0306aaeced292`
and matched the original ZIP member in a later check. CDP reported revision
`fb096c0011f9d50f0a264a9376420cdea9c421e3`. This is an unmodified test browser,
not this project's custom browser.

All runs used fresh owned profiles, a loopback fixture server, and an explicitly
selected local executable. The user's normal Chrome/profile was untouched. The
reference extension was loaded unpacked from the archived source. No debugging
focus emulation or lifecycle override is used by `tests/run.mjs`.

## Accepted observations

`extension-1/results.json` under ignored `.runtime/oracle/` has SHA-256
`8386fd327ad085338d2a7e8bd4e9543eced8e9c03382899025918a7bdb0b1811`.
This direct CDP-controlled run verified a genuinely hidden document by calling
the original prototype getters: native hidden was true/native visibility was
hidden while the instance getters reported false/visible and focus true.
Same-origin, cross-origin, and about:blank frames reported protected state.
The run also recorded:

- Visibility events reached a website window capture listener even though the
  extension blocked document listeners.
- A hidden-started animation chain produced three callbacks in 1.3 seconds;
  its native timer fallback remained throttled.
- An ordinary hidden `location.href` redirect succeeded.
- Fullscreen protection enabled: real entry succeeded, switching tabs exited
  fullscreen, and both spoofed/native element getters returned null. Fullscreen
  events were delivered. It did not preserve the claimed practical state.
- Disabling the `hidden`/`visibilityState` preferences did not restore those
  getters.
- Late attachment changed getters but pre-existing blur/visibility handlers
  still ran.

This early harness run was **not an overall pass**: an initially overbroad
event assertion incorrectly expected the extension to block ancestor capture
listeners, and unpacked MV3 reload required enabling developer mode. Those
harness assumptions were fixed. The individual raw measurements above remain
valid evidence; they are not a claim that the full test suite passed.

The accepted baseline REA process capture is
`ev_b25e6e2c9b58143ec286b51201e98982785dfe9b353349a8fc0e4489857546aa`.
It ran the real test executable/controller against the unmodified browser,
exited 0, and passed all **17 then-current assertions**, including unpacked MV3
installation, worker messaging/storage, version-changing reload, restart
persistence, and removal. Its report `baseline-rea2/results.json` SHA-256 is
`272fe80230bd36d8b341c3f189d8cda8738aad83a0c4597c4d4b23eb98b4984f`.
Later harness additions (window identity, cancellation, optional assertions)
are not included in that historical 17-check pass.

The baseline measured fullscreen exit callbacks while the native document was
still **visible and focused**, before the eventual hidden state. Therefore a
safe hidden-only snapshot cannot guarantee retention after this macOS tab
switch. Retaining every visible exit would leave stale state after a user's
intentional Escape/exit action. The optional native test records this case as
uncovered for snapshot retention, and independently asserts hidden event
filtering and normal foreground exit when a custom binary is available.

REA process-capture limits apply: sampled process trees can miss short-lived
children, filesystem observations are before/after snapshots, inherited ambient
environment is not recorded, and executable hashing is a prelaunch sample,
not atomic OS image binding. These are controlled integration results, not a
formal proof of browser equivalence.

## Excluded runs and unresolved runtime anomaly

Later reference runs (`extension-rea` and `extension-3`) reported native
prototype visibility as visible even for an inactive tab in the same window.
Their fast animation counts and absent visibility transitions cannot establish
hidden-page behavior. The harness now explicitly fails such an oracle run.
`extension-rea` had superficially passed its previous 23 assertions, but that
pass is **excluded** from background-equivalence claims. Its REA ID is
`ev_971adfbff3db7ee3ba28c37b754ca823f20dc0d2e848d9e167b77cf588893c4f`
and report SHA-256 is `f9e8a70752b04fc4618f8b14dc7e3e88e361f855329bfcded15650cfad4e14ee`.

Diagnostics confirmed that both controlled tabs had the same native window ID,
the cover tab was active, the main tab inactive, and an isolated-world native
getter also returned visible. Explicitly turning off focus emulation in a
separate diagnostic did not change it. The CFT executable still matched its
ZIP. No cause is established. This observation remains unresolved rather than
being used to inflate the extension's capability or callback rate.

The runtime REA session was exported to ignored
`.runtime/oracle/rea-runtime-evidence.json` (6 records, 507199 bytes, SHA-256
`4e78938958936175b8fb95563bab80c9b808a0a112148e359845f3bf05ad4f95`).
It contains machine/process metadata and is not intended as a public release
artifact. Public CI should upload only the finite `results.json` and
`browser.log` outputs described in [tests/README.md](../tests/README.md).

## Required before a completed-browser claim

- Run the default native tests on actual built macOS arm64 and Windows x64
  packages, plus a master-feature-disabled baseline on the same binaries.
- Run optional fullscreen/reload tests; report ordering-limited snapshot cases
  separately and obtain a genuine hidden-exit case before claiming snapshot
  retention.
- Repeat a validated, truly hidden reference-extension run on both platforms.
  The current Windows oracle coverage is absent.
- Verify normal browser UI visually, standard Chrome Web Store installation,
  and supported extension store-update/removal behavior on both platforms.
  The unpacked MV3 fixture is not a store-service test.
- Keep freeze/discard/sleep, indefinite scheduling, every third-party extension,
  and Google-restricted services outside the tested claims unless separately
  verified.
