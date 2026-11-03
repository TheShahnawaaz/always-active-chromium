# Browser identity and distribution

The Mac development package passed fresh extraction, native behavior and normal
Store verification in run 41533441385. Windows passed real per-user installation,
all behavior modes and normal Store verification in run 41663769161. Both actual
normal-window images were visually reviewed. Exact results and limits are in
PROGRESS.md, UI-REVIEW.md and the platform release documentation.

## Appearance and identity

The application uses the standard Chromium interface from the pinned stable
release, with the native behavior patch as its only feature change. There are
no new toolbar controls, settings pages, badges, or debugging banners. Chromium's
name and artwork remain: the private Google Chrome branding assets are not
available in the public source tree. See upstream's
[Google Chrome branded builds](https://chromium.googlesource.com/chromium/src/+/156.0.8078.80/docs/google_chrome_branded_builds.md).

The public build omits Chromium's missing-Google-API-key informational startup
notice to keep ordinary startup close to Chrome. This does not configure a key
or enable a Google service; security, OS and encryption warnings retain their
upstream paths. The exact narrow change is documented in the native behavior
notes.

The app must coexist with stock Google Chrome. Its installation, browser data,
and test profiles must never reuse or replace the user's Google Chrome files.
Ordinary extension support and Chrome Web Store integration remain enabled.
Compatibility with restricted Google services, Google account sync, DRM
components, and individual third-party extensions requires separate evidence;
retaining Chromium's extension system alone does not establish those results.

## Extension verification

The pinned source enables desktop extensions on Mac/Windows without a branding
gate in [buildflags.gni](https://github.com/chromium/chromium/blob/fb096c0011f9d50f0a264a9376420cdea9c421e3/extensions/buildflags/buildflags.gni#L43).
The stable [Store API declaration](https://github.com/chromium/chromium/blob/fb096c0011f9d50f0a264a9376420cdea9c421e3/extensions/common/api/_api_features.json#L967)
allows the real Chrome Web Store origin. Native install approval, CRX signature
and origin checks remain unchanged. In addition to this source evidence, actual
Mac delivery 41533441385 passed all 20 normal uBlock Origin Lite Store phases.
The corresponding Windows package remains unverified.

Release verification must use a fresh owned profile, minimal launch flags, the
actual Store Add button, and the actual identified, enabled native permission
button. The [normal dialog](https://github.com/chromium/chromium/blob/fb096c0011f9d50f0a264a9376420cdea9c421e3/chrome/browser/ui/views/extensions/extension_install_dialog_view.cc#L260)
defaults to Cancel and briefly disables acceptance; blind Enter and test-only
auto-confirm hooks are unsuitable. Verify functionality and persistence after
restart, then normal update-check and removal paths on each OS. Do not alter
Store URLs, signatures, permission prompts, policies or OS accessibility
protections to manufacture a passing result.

The extensions page's [Update action](https://github.com/chromium/chromium/blob/fb096c0011f9d50f0a264a9376420cdea9c421e3/chrome/browser/extensions/api/developer_private/developer_private_functions.cc#L451)
performs a real foreground updater check. A completed check with no newer
version proves only that path. An actual Store version upgrade needs an older
Store-installed version and a newer real Store release. The automated unpacked
MV3 fixture verifies APIs, reload, storage, restart and removal separately; it
cannot establish Store installation or automatic Store upgrade.

## Build and package requirements

Both targets compile on standard GitHub-hosted runners: macOS arm64 and Windows
x64. Source archives and build checkpoints are versioned and checksummed.
Build logs, package checksums, native behavior test results, and extension
compatibility results must accompany verified packages. The pipeline must
preserve Chromium's bundled notices and generated third-party credits.

Signing status must be stated for each artifact. No Developer ID certificate,
Apple notarization credential, or Windows signing certificate has been provided
to the project. No signing identity may be purchased or uploaded implicitly.

The Mac packager seals a fresh staged copy with an ad-hoc identity after
inspecting the real compiled signatures. It preserves existing entitlements and
refuses unsupported enforcement flags or non-ad-hoc identities. It signs nested
code before the containing framework/app, then requires strict verification.
It leaves the compiler outputs unchanged and archives the sealed copy. This is
development-package sealing, without Developer ID or notarization; it does not
change Gatekeeper, TCC, quarantine or other OS settings. The complete delivered
archive must still pass fresh extraction and browser/extension/runtime checks.

## Verify the delivered package

After a real package draft exists, run **Actions → Verify real browser delivery**
with its exact `ci-source-<commit12>` tag and one platform. This uses a fresh
standard GitHub-hosted runner. It verifies the source/final tags, package/build
checksums, exact pins and native fingerprint before opening the package.

macOS tests the ZIP after `ditto` extraction, code-signature structure,
architecture and bundle-identity checks. Windows requires no existing Chromium
installation or registration, runs the real default per-user installer with
`--do-not-launch-chrome`, and tests its installed
`%LOCALAPPDATA%\Chromium\Application\chrome.exe`. It never substitutes the build
output or a reference browser. Both routes create separate owned test profiles.

The delivered executable runs the existing master-off, native-default,
optional-feature and paired no-debug checks, followed by the reviewed normal
Store install/execution/restart/update-check/removal flow. Reports bind the
acquired executable to its canonical path, size and SHA-256. Bounded JSON,
checksums and at most one verified owned-window PNG go to a separate
`delivery-verification-*` draft; profiles, browser logs, packages and extension
source are excluded. Missing or partial evidence
cannot produce a verified result. Signing/notarization and a genuine Store
version upgrade remain separate from these checks.

Windows delivery enables an optional full-window capture during the native
no-debug phase. The helper requires the exact owned PID/profile/executable/start
and a normal foreground window, then uses `PrintWindow` with a 15-second external
deadline. The PNG is limited to 2048×1536, 3,145,728 pixels and 3 MiB, with bounds,
identity, complete PNG structure and hash checked before publication. There is
no desktop fallback, input simulation or browser-debug capture. Capture errors
remain separate from runtime/Store outcomes. A retained image is **pending manual
visual review**; API success and nonuniform pixels do not establish complete
rendering or UI equivalence. No Mac recording permission is requested.

The Mac verifier now optionally captures its task-owned foreground fixture
window through the system `screencapture -l` window-only route, with no shadow.
It first checks existing screen-capture and accessibility permission; unavailable
permission produces an unsupported receipt without a prompt. Kernel executable,
argv/profile, owner, process-group/session and microsecond start identity,
focused standard AX window, window-server PID/title/bounds and unchanged state
are checked before and after capture. Only the matching fixture window ID is
passed to the capture tool. A private temporary directory and exclusive final
PNG creation limit output to the owned test directory. The existing finite PNG,
hash and native-run/extracted-executable binding checks apply. Hosted compilation,
invalid-PID refusal and actual capture passed. A diagnostic established identical
owned AX/CG geometry with differing full title strings; each fixture title is
verified independently and remains equal to its own initial value throughout
capture. The real Mac image was visually inspected as recorded in UI-REVIEW.md.
Synthetic schema tests alone are not native UI evidence.

For a separately reviewed reference-only capture trial, the existing passive
controller accepts `AA_WINDOW_CAPTURE_HELPER` and `AA_WINDOW_CAPTURE_MODE=control`
with `--mode control`. That produces reference capture mechanics evidence only;
it cannot establish custom-package or native-feature success.

The reference workflow also explicitly opts into failed-startup diagnostics.
After failed observations it may capture the same freshly reverified owned
foreground window, accepting only the fixture title or a finite known Untitled
title. Its receipt labels `startup-diagnostic`, records title/identity rechecks,
and keeps behavior/equivalence unverified. The reference publisher can retain
those pixels while the test and workflow remain failed. This mode is rejected
for native or paired runs; ordinary delivery image validation stays fixture-only.

The initial flags-0 capture returned a solid image on the verified hosted CFT
window and was rejected. The next implementation uses full-window flag
[`PW_RENDERFULLCONTENT = 2`](https://microsoft.github.io/windows-docs-rs/doc/windows/Win32/UI/WindowsAndMessaging/constant.PW_RENDERFULLCONTENT.html),
also used by [WebRTC's window capturer](https://webrtc.googlesource.com/src/+/7f509e13139a9683b2fd548a2e5270e9da057763/modules/desktop_capture/win/window_capturer_win_gdi.cc)
for DirectComposition windows. It still makes one window-only API attempt;
there is no desktop fallback or relaxation of the blank-image/ownership checks.
Actual image quality and completeness require observed pixels and manual review.

## Installation procedure

These instructions describe the packages. **Both platforms have passed fresh
delivery/Store checks and normal-window visual review.**
Use only a package explicitly accompanied
by passing delivery evidence and its matching SHA-256 manifest. Compiler
checkpoints and diagnostic drafts are not browser downloads.

Download the package and `always-active-chromium-156.0.8078.80-<platform>-SHA256SUMS.txt`
from the same build release. Verify the package against the matching filename
in that manifest before opening it. Release notes must also state the exact
source tag and link the fresh-delivery verification run.

### macOS Apple Silicon

The package is `always-active-chromium-156.0.8078.80-mac-arm64.zip`. In Terminal,
from its download directory, calculate:

```sh
shasum -a 256 always-active-chromium-156.0.8078.80-mac-arm64.zip
```

Compare the entire 64-character result with the ZIP entry in the manifest.
Extract the ZIP with Archive Utility, then move `Chromium.app` into Applications.
If an existing Chromium app is present, keep it and choose a separate folder;
do not replace it or Google Chrome. Open the extracted application normally.
This is an arm64 app for Apple Silicon, not an Intel Mac package. Its bundle and
main Mach-O declare macOS 13.0 minimum; runtime checks were performed on macOS 26.

The app is ad-hoc signed, without Developer ID or notarization. A browser-downloaded
ZIP may therefore receive Gatekeeper treatment that a hosted extraction test
does not exercise. Follow the release's observed first-launch notes and normal
macOS approval UI when available. Do not disable Gatekeeper or remove quarantine
as part of installation. No accessibility or screen-recording permission is
needed for the browser's native always-active behavior.

### Windows x64

The package is `always-active-chromium-156.0.8078.80-win-x64-installer.exe`.
In PowerShell, from its download directory, calculate:

```powershell
Get-FileHash .\always-active-chromium-156.0.8078.80-win-x64-installer.exe -Algorithm SHA256
```

Compare the complete hash with the installer entry in the manifest. Run the
installer as the current user. The normal per-user destination is
`%LOCALAPPDATA%\Chromium\Application\chrome.exe`; it is separate from Google
Chrome. If another Chromium installation already exists, stop before installing
to avoid replacing it. The installer has no Authenticode certificate; a hash
match establishes agreement with the release manifest, not a trusted publisher
signature. Use normal Windows approval UI without changing system protections.

### First launch and extensions

Use this app's Chromium profile. Never pass Google Chrome's profile directory
to it, copy a Chrome profile into it, or select this app as the default browser
unless that is desired. An existing standalone Chromium profile also belongs
to that installation; an explicit `--user-data-dir` pointing to a new dedicated
directory can keep it separate. The always-active feature is enabled by default
for supported web documents, with no extension or debugging helper required.

Open the Chrome Web Store through the ordinary browser interface and use its
normal Add and permission prompts for supported desktop Manifest V3 extensions.
The release evidence must identify the extension and exact operations actually
verified. An update check returning `no_update` does not prove a future version
upgrade. See the native behavior notes for optional CLI controls and finite
behavior limits.

## Updates

This project does not distribute official Google Chrome or enroll its builds
in Google's Chrome update channel. Updating means pinning a newer stable
Chromium release, reviewing/reapplying the small native patch, building both
targets again, and rerunning behavior and extension checks. An update service
for this project has not been implemented.

GitHub Releases are the planned package distribution channel. Intermediate
build checkpoints must be clearly marked as build state, not installable
browser releases. GitHub documents a limit of 2 GiB per release asset, with no
total release-size or bandwidth limit in
[About releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases#storage-and-bandwidth-quotas).
