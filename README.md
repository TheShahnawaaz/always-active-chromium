# Always Active Chromium

Work in progress: a desktop Chromium build with native always-visible/focused
behavior for macOS Apple Silicon and Windows x64, while retaining Chromium's
standard interface and extension support.

**There is no custom browser binary yet.** The implementation goal is active.
The repository currently records the requirements and contains a manually
triggered GitHub-hosted runner preflight.

## Requirements

- Implement the observed behavior of
  [Always active Window - Always Visible](https://chromewebstore.google.com/detail/always-active-window-alwa/ehllkhjndgnlokhomdlhgbineffifcbj)
  in Chromium's native browser/renderer code. The investigated artifact is version
  0.4.8; recheck the shipped version before implementation.
- Cover visibility/hidden getters, document focus, relevant focus/visibility,
  mouse and pointer events, animation scheduling, and the extension's optional
  fullscreen and attempted background-navigation behavior. Record observed
  behavior and limitations separately from marketing claims.
- Enable the native feature by default for ordinary websites and frames, with
  native command-line compatibility controls as needed. Do not implement the feature using an
  extension, injected JavaScript, or an attached debugging helper.
- Start from pinned current stable Chromium 156.0.8078.80
  (`fb096c0011f9d50f0a264a9376420cdea9c421e3`) and preserve its normal interface.
  Do not add toolbar buttons, feature settings pages, status badges, debugging
  banners, or other visual changes. Google's private branding and restricted
  services remain documented differences from official Chrome.
- Preserve the normal extensions platform and Chrome Web Store integration.
  Verify installation, execution, restart persistence, update behavior, and
  removal of representative supported Manifest V3 extensions on both platforms.
  Do not claim compatibility with every legacy, ChromeOS-only, or
  Google-service-dependent extension.
- Keep stock Chrome, its installed extensions, and its existing user profiles
  untouched. Use a distinct app identity and separate browser profile.
- Document differences from official Chrome, including branding, restricted
  Google services, signing, and the update process.

## Build-compute constraint

All builds must use **GitHub-hosted runners only**. No AWS resources, Depot,
external cloud builders, or self-hosted build runners. In particular, AWS Mac is
prohibited. Do not silently fall back to another provider.

Use standard GitHub-hosted runners first. No paid runner, plan upgrade, or
additional storage spending is authorized. Measure available resources, use a
minimal source checkout/build configuration, and investigate resumable build
stages to stay within runner time limits. If the constrained route cannot finish,
report the measured blocker rather than declaring success.

Upstream ungoogled-chromium workflows are references for CI techniques only;
this project is not intended to remove Chromium's Google Web Store integration.
Its historical Mac workflow used GitHub-hosted runners, while the current Mac
workflow uses an external provider and is not an acceptable build route here.

## Verification and completion

Completion requires real, launchable macOS arm64 and Windows x64 packages;
feature-by-feature tests against ordinary Chromium and the extension's observed
behavior; ordinary extension compatibility checks; build logs, checksums, and
clear installation/known-limitations documentation. A workflow definition or
successful preflight alone is not a completed browser build.

## Runner preflight

Run **Actions -> Runner preflight -> Run workflow** to inspect the standard
GitHub-hosted Mac and Windows environments. This checks capacity and toolchain
versions without fetching Chromium, building a browser, uploading large
artifacts, or modifying the runners' installed software.
