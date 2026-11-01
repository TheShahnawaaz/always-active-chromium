# Project constraints

- Build compute must be GitHub-hosted only. Never use AWS Mac or other AWS
  resources for this project. Do not use Depot, other external cloud builders,
  or self-hosted runners as a fallback.
- No paid runner, account upgrade, or additional paid artifact/cache storage is
  authorized. Keep the public repository free of credentials and personal data.
- Keep the full Chromium checkout and compilation outputs off the local Mac.
  Local work should remain limited to small patches, tests, scripts, and reports.
- Implement the always-active behavior natively, not as an extension, injected
  script, or debugging connection that must remain attached during normal use.
- Retain the standard desktop extension system and Chrome Web Store integration;
  verify representative supported Manifest V3 extensions on macOS and Windows.
- Preserve the standard Chromium UI. Do not add toolbar buttons, settings pages,
  badges, banners, or other visual changes. Native CLI toggles are acceptable for
  compatibility options without changing the default interface.
- Do not modify, replace, or reuse the user's stock Chrome installation/profile.
- Distinguish observed extension behavior, implementation choices, test results,
  and unknowns. Do not claim a completed browser from CI configuration alone.
- Read README.md for the intended targets and completion criteria. The goal is
  active; do not claim native browser binaries exist until built and verified.
