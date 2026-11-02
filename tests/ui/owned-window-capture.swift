// One task-owned foreground fixture window only. Never requests OS permissions.
// The existing kernel argv/executable/start checks are shared in design with store-ui.swift.
import Foundation
import ApplicationServices
import AppKit
import CryptoKit
import Darwin

let deadline = ProcessInfo.processInfo.systemUptime + 10
struct ProbeError: Error { let message: String }
func checkBudget() throws {
    if ProcessInfo.processInfo.systemUptime >= deadline { throw ProbeError(message: "capture_budget_exceeded") }
}
var report: [String: Any] = [
    "schema": 1, "purpose": "owned-normal-browser-window-capture", "platform": "darwin",
    "status": "refused", "captureContext": "fixture", "behaviorVerified": false,
    "captureAttempted": false, "captureSucceeded": false, "captureOutcomeUncertain": false,
    "nativeUiAccessed": false, "visitedWindows": 0, "manualReview": "pending",
    "uiEquivalenceVerified": false, "visualCompletenessVerified": false,
    "identity": ["verified": false], "window": [String: Any](),
    "png": [String: Any](), "errors": [String]()
]
func finish() -> Never {
    guard let data = try? JSONSerialization.data(withJSONObject: report, options: [.sortedKeys]), data.count <= 65536 else {
        print("{\"schema\":1,\"status\":\"error\",\"errors\":[\"serialization_failed\"]}"); exit(1)
    }
    FileHandle.standardOutput.write(data); FileHandle.standardOutput.write(Data([10])); exit(0)
}
func run(_ executable: String, _ arguments: [String], text: Bool = false) throws -> String {
    try checkBudget()
    let process = Process(); process.executableURL = URL(fileURLWithPath: executable); process.arguments = arguments
    let pipe = Pipe(); process.standardOutput = text ? pipe : FileHandle.nullDevice
    process.standardError = FileHandle.nullDevice; process.standardInput = FileHandle.nullDevice
    try process.run()
    while process.isRunning {
        if ProcessInfo.processInfo.systemUptime >= deadline { process.terminate(); throw ProbeError(message: "capture_subprocess_deadline") }
        usleep(20_000)
    }
    guard process.terminationStatus == 0 else { throw ProbeError(message: "capture_subprocess_failed") }
    if !text { return "" }
    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    guard data.count <= 256, let result = String(data: data, encoding: .utf8) else { throw ProbeError(message: "invalid_creation_identity") }
    return result.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
}
func canonical(_ path: String, directory: Bool) throws -> String {
    guard path.hasPrefix("/"), !path.utf8.contains(0) else {
        throw ProbeError(message: "absolute_paths_required")
    }
    let resolved = URL(fileURLWithPath: path).resolvingSymlinksInPath().standardizedFileURL.path
    var isDirectory: ObjCBool = false
    guard FileManager.default.fileExists(atPath: resolved, isDirectory: &isDirectory),
          isDirectory.boolValue == directory else {
        throw ProbeError(message: "expected_path_type_missing")
    }
    return resolved
}

struct Identity: Equatable {
    let executable: String
    let startSeconds: UInt64
    let startMicroseconds: UInt64
}

func identity(_ pid: pid_t, profile: String, executable: String) throws -> Identity {
    var info = proc_bsdinfo()
    let size = MemoryLayout<proc_bsdinfo>.size
    guard proc_pidinfo(pid, PROC_PIDTBSDINFO, 0, &info, Int32(size)) == size,
          info.pbi_uid == getuid(), getpgid(pid) == pid, getsid(pid) == pid else {
        throw ProbeError(message: "process_missing_or_owner_mismatch")
    }
    var executableBuffer = [CChar](repeating: 0, count: Int(MAXPATHLEN) * 4)
    guard proc_pidpath(pid, &executableBuffer, UInt32(executableBuffer.count)) > 0 else {
        throw ProbeError(message: "process_executable_unavailable")
    }
    let actualExecutable = try canonical(String(cString: executableBuffer), directory: false)
    guard actualExecutable == executable else {
        throw ProbeError(message: "process_executable_mismatch")
    }

    // Read only this PID's argv from the kernel; never emit the command line.
    var mib: [Int32] = [CTL_KERN, KERN_PROCARGS2, pid]
    var bytes = 0
    guard sysctl(&mib, u_int(mib.count), nil, &bytes, nil, 0) == 0,
          bytes >= 4, bytes <= 262_144 else {
        throw ProbeError(message: "process_arguments_unavailable_or_oversized")
    }
    var buffer = [UInt8](repeating: 0, count: bytes)
    guard sysctl(&mib, u_int(mib.count), &buffer, &bytes, nil, 0) == 0 else {
        throw ProbeError(message: "process_arguments_unavailable")
    }
    buffer = Array(buffer.prefix(bytes))
    let argc = buffer.prefix(4).withUnsafeBytes { $0.loadUnaligned(as: Int32.self) }
    guard argc > 0, argc <= 4096 else { throw ProbeError(message: "invalid_process_arguments") }
    var offset = 4
    while offset < buffer.count && buffer[offset] != 0 { offset += 1 }
    while offset < buffer.count && buffer[offset] == 0 { offset += 1 }
    var arguments: [String] = []
    for _ in 0..<argc {
        let start = offset
        while offset < buffer.count && buffer[offset] != 0 { offset += 1 }
        guard offset < buffer.count,
              let argument = String(bytes: buffer[start..<offset], encoding: .utf8) else {
            throw ProbeError(message: "invalid_process_arguments")
        }
        arguments.append(argument)
        offset += 1
    }
    var profiles: [String] = []
    for (index, argument) in arguments.enumerated() {
        if argument.hasPrefix("--user-data-dir=") {
            profiles.append(String(argument.dropFirst("--user-data-dir=".count)))
        } else if argument == "--user-data-dir", index + 1 < arguments.count {
            profiles.append(arguments[index + 1])
        }
    }
    guard profiles.count == 1,
          try canonical(profiles[0], directory: true) == profile else {
        throw ProbeError(message: "process_profile_mismatch")
    }
    guard !arguments.contains(where: { $0.hasPrefix("--remote-debugging") || $0.hasPrefix("--enable-automation") || $0.hasPrefix("--headless") || $0.hasPrefix("--load-extension") || $0.hasPrefix("--disable-extensions-except") || $0.hasPrefix("--enable-unsafe-extension-debugging") }) else { throw ProbeError(message: "normal_launch_flags_required") }
    return Identity(executable: actualExecutable,
                    startSeconds: info.pbi_start_tvsec,
                    startMicroseconds: info.pbi_start_tvusec)
}


func ax(_ element: AXUIElement, _ name: CFString) throws -> CFTypeRef? {
    try checkBudget()
    var result: CFTypeRef?
    let status = AXUIElementCopyAttributeValue(element, name, &result)
    guard status == .success else { throw ProbeError(message: "owned_window_attribute_unavailable") }
    return result
}
func axRect(_ window: AXUIElement) throws -> CGRect {
    guard let p = try ax(window, kAXPositionAttribute as CFString), CFGetTypeID(p) == AXValueGetTypeID(),
          let s = try ax(window, kAXSizeAttribute as CFString), CFGetTypeID(s) == AXValueGetTypeID() else { throw ProbeError(message: "owned_window_bounds_unavailable") }
    var origin = CGPoint.zero; var size = CGSize.zero
    guard AXValueGetValue(unsafeBitCast(p, to: AXValue.self), .cgPoint, &origin),
          AXValueGetValue(unsafeBitCast(s, to: AXValue.self), .cgSize, &size) else { throw ProbeError(message: "owned_window_bounds_unavailable") }
    let rect = CGRect(origin: origin, size: size)
    guard [rect.origin.x, rect.origin.y, rect.width, rect.height].allSatisfy({ $0.isFinite }), rect.width >= 320, rect.height >= 240, rect.width <= 2048, rect.height <= 1536 else { throw ProbeError(message: "owned_window_bounds_unsupported") }
    return rect
}
struct WindowState: Equatable { let id: CGWindowID; let title: String; let rect: CGRect; let count: Int }
func windowState(_ pid: pid_t) throws -> WindowState {
    try checkBudget()
    guard NSWorkspace.shared.frontmostApplication?.processIdentifier == pid,
          let app = NSRunningApplication(processIdentifier: pid), !app.isHidden, !app.isTerminated else { throw ProbeError(message: "owned_foreground_application_required") }
    let application = AXUIElementCreateApplication(pid); _ = AXUIElementSetMessagingTimeout(application, 0.2)
    guard let windows = try ax(application, kAXWindowsAttribute as CFString) as? [AXUIElement], !windows.isEmpty, windows.count <= 8,
          let focusedRaw = try ax(application, kAXFocusedWindowAttribute as CFString), CFGetTypeID(focusedRaw) == AXUIElementGetTypeID() else { throw ProbeError(message: "owned_window_limit_or_focus") }
    let focused = unsafeBitCast(focusedRaw, to: AXUIElement.self)
    guard let window = windows.first(where: { CFEqual($0, focused) }) else { throw ProbeError(message: "owned_focused_window_missing") }
    var owner: pid_t = 0
    guard AXUIElementGetPid(window, &owner) == .success, owner == pid,
          try ax(window, kAXSubroleAttribute as CFString) as? String == "AXStandardWindow",
          (try ax(window, kAXMinimizedAttribute as CFString) as? NSNumber)?.boolValue == false,
          let title = try ax(window, kAXTitleAttribute as CFString) as? String, title.utf8.count <= 512,
          title.hasPrefix("Native visibility observation") else { throw ProbeError(message: "normal_owned_fixture_window_required") }
    let rect = try axRect(window)
    guard let all = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] else { throw ProbeError(message: "window_server_metadata_unavailable") }
    let owned = all.filter { ($0[kCGWindowOwnerPID as String] as? NSNumber)?.int32Value == pid }
    guard owned.count <= 8 else { throw ProbeError(message: "owned_window_limit") }
    report["visitedWindows"] = owned.count
    func finiteRect(_ rect: CGRect) -> [String: Double] {
        ["x": Double(rect.origin.x), "y": Double(rect.origin.y), "width": Double(rect.width), "height": Double(rect.height)]
    }
    report["windowDiagnostic"] = ["scope": "owned-pid-window-metadata-only", "axFixtureTitleVerified": true,
        "axBounds": finiteRect(rect), "candidates": owned.map { item -> [String: Any] in
            let name = item[kCGWindowName as String] as? String
            var value: [String: Any] = ["handle": (item[kCGWindowNumber as String] as? NSNumber)?.uint32Value ?? 0,
                "layer": (item[kCGWindowLayer as String] as? NSNumber)?.intValue ?? -999,
                "alpha": (item[kCGWindowAlpha as String] as? NSNumber)?.doubleValue ?? -1,
                "nameAvailable": name != nil, "titleMatchesAX": name == title,
                "fixtureTitleVerified": name?.hasPrefix("Native visibility observation") == true]
            if let bounds = item[kCGWindowBounds as String] as? [String: Any],
               let frame = CGRect(dictionaryRepresentation: bounds as CFDictionary) { value["bounds"] = finiteRect(frame); value["boundsMatchAX"] = frame == rect }
            return value
        }]
    let candidates = owned.filter { item in
        guard (item[kCGWindowLayer as String] as? NSNumber)?.intValue == 0,
              (item[kCGWindowAlpha as String] as? NSNumber)?.doubleValue == 1,
              item[kCGWindowName as String] as? String == title,
              let bounds = item[kCGWindowBounds as String] as? [String: Any],
              let cgRect = CGRect(dictionaryRepresentation: bounds as CFDictionary) else { return false }
        return cgRect == rect
    }
    guard candidates.count == 1, let number = candidates[0][kCGWindowNumber as String] as? NSNumber, number.uint32Value != 0 else { throw ProbeError(message: "unique_owned_window_id_unavailable") }
    return WindowState(id: number.uint32Value, title: title, rect: rect, count: owned.count)
}
var temporary: URL?
do {
    var args: [String: String] = [:]
    let values = Array(CommandLine.arguments.dropFirst())
    guard values.count == 14 else { throw ProbeError(message: "invalid_arguments") }
    for index in stride(from: 0, to: values.count, by: 2) {
        guard ["--pid", "--profile", "--executable", "--expected-started", "--output", "--context", "--purpose"].contains(values[index]), args[values[index]] == nil else { throw ProbeError(message: "invalid_arguments") }
        args[values[index]] = values[index + 1]
    }
    guard let pidText = args["--pid"], let pid = Int32(pidText), pid > 1,
          args["--context"] == "fixture", args["--purpose"] == "appearance",
          let expected = args["--expected-started"], !expected.isEmpty, expected.utf8.count <= 80,
          let profileText = args["--profile"], let executableText = args["--executable"], let output = args["--output"] else { throw ProbeError(message: "invalid_owned_identity") }
    let profile = try canonical(profileText, directory: true), executable = try canonical(executableText, directory: false)
    let parent = try canonical(URL(fileURLWithPath: output).deletingLastPathComponent().path, directory: true)
    guard URL(fileURLWithPath: profile).deletingLastPathComponent().path == parent,
          output == parent + "/browser-window.png", !FileManager.default.fileExists(atPath: output) else { throw ProbeError(message: "exclusive_owned_output_required") }
    let original = try identity(pid, profile: profile, executable: executable)
    guard try run("/bin/ps", ["-p", String(pid), "-o", "lstart="], text: true) == expected else { throw ProbeError(message: "creation_identity_mismatch") }
    report["identity"] = ["pid": pid, "profile": profile, "executable": executable, "started": expected,
                          "startSeconds": original.startSeconds, "startMicroseconds": original.startMicroseconds,
                          "verified": true, "ownerVerified": true, "sessionVerified": true]
    guard CGPreflightScreenCaptureAccess() else {
        report["status"] = "unsupported"; throw ProbeError(message: "screen_capture_permission_unavailable")
    }
    guard AXIsProcessTrusted() else {
        report["status"] = "unsupported"; throw ProbeError(message: "accessibility_permission_unavailable")
    }
    report["nativeUiAccessed"] = true
    let before = try windowState(pid)
    report["visitedWindows"] = before.count
    guard try identity(pid, profile: profile, executable: executable) == original else { throw ProbeError(message: "identity_changed_before_capture") }
    var owned = report["identity"] as! [String: Any]; owned["immediatelyRevalidated"] = true; report["identity"] = owned
    guard try windowState(pid) == before else { throw ProbeError(message: "window_changed_before_capture") }
    let temp = URL(fileURLWithPath: parent).appendingPathComponent(".owned-capture-" + UUID().uuidString, isDirectory: true)
    try FileManager.default.createDirectory(at: temp, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700]); temporary = temp
    let candidate = temp.appendingPathComponent("window.png")
    report["captureAttempted"] = true; report["captureSucceeded"] = NSNull(); report["captureOutcomeUncertain"] = true
    _ = try run("/usr/sbin/screencapture", ["-x", "-o", "-t", "png", "-l", String(before.id), candidate.path])
    guard try identity(pid, profile: profile, executable: executable) == original, try windowState(pid) == before,
          try run("/bin/ps", ["-p", String(pid), "-o", "lstart="], text: true) == expected else { throw ProbeError(message: "identity_or_window_changed_after_capture") }
    let properties = try candidate.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
    guard properties.isRegularFile == true, properties.isSymbolicLink == false,
          let size = properties.fileSize, size >= 57, size <= 3145728 else { throw ProbeError(message: "png_type_or_size_invalid") }
    let data = try Data(contentsOf: candidate)
    guard let image = NSBitmapImageRep(data: data), image.pixelsWide >= 320, image.pixelsHigh >= 240,
          image.pixelsWide <= 2048, image.pixelsHigh <= 1536, image.pixelsWide * image.pixelsHigh <= 3145728 else { throw ProbeError(message: "png_dimensions_unsupported") }
    let scaleX = Double(image.pixelsWide) / Double(before.rect.width), scaleY = Double(image.pixelsHigh) / Double(before.rect.height)
    guard scaleX >= 1, scaleX <= 3, abs(scaleX - scaleY) < 0.01 else { throw ProbeError(message: "window_pixel_scale_mismatch") }
    var colors = Set<String>()
    for y in 0..<24 { for x in 0..<32 {
        guard let color = image.colorAt(x: x * image.pixelsWide / 32, y: y * image.pixelsHigh / 24)?.usingColorSpace(.deviceRGB) else { throw ProbeError(message: "png_sample_unavailable") }
        colors.insert("\(Int((color.redComponent * 255).rounded()))-\(Int((color.greenComponent * 255).rounded()))-\(Int((color.blueComponent * 255).rounded()))")
    }}
    guard colors.count >= 2 else { throw ProbeError(message: "solid_capture_refused") }
    try checkBudget()
    let fd = open(output, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0o600)
    guard fd >= 0 else { throw ProbeError(message: "exclusive_owned_output_required") }
    let file = FileHandle(fileDescriptor: fd, closeOnDealloc: true); try file.write(contentsOf: data); try file.synchronize(); try file.close()
    owned["afterCaptureRevalidated"] = true; report["identity"] = owned
    report["window"] = ["handle": String(before.id, radix: 16), "ownerPID": pid, "foregroundVerified": true,
        "visible": true, "minimized": false, "normalTopLevelVerified": true, "fixtureTitleVerified": true,
        "titleKind": "fixture", "unchangedAfterCapture": true, "width": image.pixelsWide, "height": image.pixelsHigh,
        "dpi": Int((72 * scaleX).rounded()), "logicalWidth": before.rect.width, "logicalHeight": before.rect.height]
    report["png"] = ["file": "browser-window.png", "width": image.pixelsWide, "height": image.pixelsHigh, "bytes": data.count,
        "sha256": SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()]
    report["contentCheck"] = ["sampleCount": 768, "uniqueSampleColors": colors.count, "nonUniform": true, "visualCompletenessVerified": false]
    report["method"] = "screencapture-owned-window-no-shadow"
    report.removeValue(forKey: "windowDiagnostic")
    report["captureSucceeded"] = true; report["captureOutcomeUncertain"] = false; report["status"] = "captured"
} catch {
    if report["captureAttempted"] as? Bool == true { report["status"] = "error" }
    report["errors"] = [(error as? ProbeError)?.message ?? "native_capture_unavailable"]
}
if let temp = temporary { try? FileManager.default.removeItem(at: temp) }
finish()
