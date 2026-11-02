# Browser identity and distribution

No installable native browser package has been verified yet. This document
records the distribution requirements; completed results belong in PROGRESS.md
and the eventual release notes.

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
and origin checks remain unchanged. This is source evidence, not a successful
Store installation on the custom build.

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

For a separately reviewed reference-only capture trial, the existing passive
controller accepts `AA_WINDOW_CAPTURE_HELPER` and `AA_WINDOW_CAPTURE_MODE=control`
with `--mode control`. That produces reference capture mechanics evidence only;
it cannot establish custom-package or native-feature success.

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
