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

## Build and package requirements

Both targets compile on standard GitHub-hosted runners: macOS arm64 and Windows
x64. Source archives and build checkpoints are versioned and checksummed.
Build logs, package checksums, native behavior test results, and extension
compatibility results must accompany verified packages. The pipeline must
preserve Chromium's bundled notices and generated third-party credits.

Signing status must be stated for each artifact. No Developer ID certificate,
Apple notarization credential, or Windows signing certificate has been provided
to the project. No signing identity may be purchased or uploaded implicitly.

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
