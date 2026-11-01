#!/usr/bin/env bash
set -euo pipefail
[[ "${GITHUB_ACTIONS:-}" == true && "${RUNNER_ENVIRONMENT:-}" == github-hosted ]] || {
  echo 'This script is restricted to ephemeral GitHub-hosted runners.' >&2; exit 1;
}
[[ "$(uname -m)" == arm64 ]] || exit 1
df -h /
xcodebuild -version
ulimit -n 10240
selected="${DEVELOPER_DIR:-$(xcode-select -p)}"
selected_app="$(python3 -c 'import pathlib,sys; p=pathlib.Path(sys.argv[1]).resolve(); print(next(v for v in (p, *p.parents) if v.name.startswith("Xcode") and v.suffix == ".app"))' "$selected")"
[[ "$selected_app" == /Applications/Xcode*.app ]] || {
  echo "Unexpected selected Xcode path: $selected_app" >&2; exit 1;
}
for candidate in /Applications/Xcode_*.app; do
  [[ -e "$candidate" && ! -L "$candidate" ]] || continue
  actual="$(python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve())' "$candidate")"
  [[ "$actual" == "$selected_app" ]] && continue
  du -sh "$candidate"
  echo "Removing unused runner Xcode bundle: $candidate"
  sudo rm -rf -- "$candidate"
done
# Xcode 26 distributes Metal as an optional public component. A successful
# compiler/linker invocation also catches placeholder executables in Xcode.
metal_probe() {
  local probe
  probe="$(mktemp -d "$RUNNER_TEMP/aacc-metal.XXXXXX")"
  cat > "$probe/check.metal" <<'METAL'
#include <metal_stdlib>
using namespace metal;
kernel void aacc_check(device uint* output [[buffer(0)]], uint i [[thread_position_in_grid]]) { output[i] = i; }
METAL
  if xcrun -sdk macosx metal -c "$probe/check.metal" -o "$probe/check.air" &&
     xcrun -sdk macosx metallib "$probe/check.air" -o "$probe/check.metallib"; then
    rm -f "$probe/check.metal" "$probe/check.air" "$probe/check.metallib"
    rmdir "$probe"
    return 0
  fi
  return 1
}
if ! metal_probe; then
  xcodebuild -downloadComponent MetalToolchain
  metal_probe
fi
# Do not alter the selected Xcode, its SDKs, the runner's home, or the workspace.
df -h /
printf 'AA_BUILD_ROOT=%s\n' /Users/runner/aacc >> "$GITHUB_ENV"
