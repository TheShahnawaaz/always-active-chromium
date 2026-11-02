# Native browser UI review

## macOS Apple Silicon — reviewed 2026-11-03 IST

The actual custom app from `ci-source-e146fe41bca3`, extracted from the
252,685,495-byte ZIP with SHA-256
`7dbfafec37054e029848f1cedff431244b3031f96ae2cc6b076305119986d2b8`,
was captured during the native-default no-debug phase of
[delivery 41533441385](https://github.com/TheShahnawaaz/always-active-chromium/actions/runs/41533441385).
The normal launch had no debugging, automation, extension-loading or emulation
flags. Runtime and normal Store verification also passed on this delivered app.

![Actual native Mac normal window](images/native-mac-arm64.png)

Codex visually inspected this actual 1000×677 PNG, asset **703329654** in draft
**432019315**, SHA-256
`540fbca5d806231a06c3a759f8b8b60a6fd5b6a5caf89e8da0a12b142c1f6f52`.
The complete normal window shows standard Mac window controls, two Chromium
tabs, the navigation/address bar, bookmark, profile and menu controls. The
expected fixture heading and body are rendered. There are no added always-active
toolbar controls, badges or startup banners visible in this view. This is a
visual inspection of native package pixels, not a synthetic image or reference
Chrome result.

The receipt binds the exact executable/profile, PID 4687, kernel start identity
and owned foreground standard window ID `104`. Both permission preflights
already passed; no permission was requested or OS setting changed. AX and
window-server titles identify the fixture and remain individually unchanged
before/after capture. Their full strings differ; they need not equal each
other. Exact window-server ID, PID and AX/CG geometry remain mandatory. All
seven delivery assets, server sizes/digests and six checksum entries were
independently verified.

The automated reports retain their original `manualReview: pending` and
`uiEquivalenceVerified: false` values. The separate
[visual review record](releases/mac-arm64/visual-review.json) records this
subsequent inspection. It covers one light-mode normal-window view; it does not
claim pixel equality with proprietary Google Chrome, every theme/settings view,
browser-download Gatekeeper approval or OS security dialogs. Chromium branding
remains a documented product difference.

## Windows x64

Native delivery and visual review are pending the existing compiler campaign.
The older CFT reference image shows a Chrome shell and an unrendered fixture;
it is not native-browser or delivery evidence. Do not substitute it for the
actual installed custom browser's capture.
