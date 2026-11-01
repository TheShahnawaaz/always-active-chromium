// Read-only native UI prerequisite probe. Never clicks, grants access, or installs.
// Compile: xcrun swiftc -O tests/ui/store-ui.swift -o OWN_OUTPUT/store-ui
// Run: store-ui --pid PID --profile ABSOLUTE_PATH --executable ABSOLUTE_PATH
import Foundation
import ApplicationServices
import AppKit
import Darwin

let maxNodes = 128
let maxDepth = 8
let maxWindows = 8
let maxStringBytes = 240
let maxOutputBytes = 65_536
let deadline = ProcessInfo.processInfo.systemUptime + 8
var truncated = false
var visited = 0
var report: [String: Any] = [
    "schema": 1, "platform": "darwin",
    "purpose": "owned-browser-native-ui-prerequisites", "status": "error",
    "identity": ["verified": false],
    "accessibility": ["trusted": NSNull(), "available": false,
                      "applicationAccessible": false, "nativeWindowAvailable": false,
                      "visibleNativeWindowAvailable": false],
    "windows": [[String: Any]](), "observedRoots": [[String: Any]](),
    "errors": [String](),
    "limits": ["maxNodes": maxNodes, "maxDepth": maxDepth,
               "maxWindows": maxWindows, "maxStringBytes": maxStringBytes,
               "maxOutputBytes": maxOutputBytes, "traversalBudgetMs": 8000]
]

struct ProbeError: Error {
    let message: String
    var status: String = "error"
}

func bounded(_ value: String) -> String {
    var result = ""
    var bytes = 0
    for scalar in value.unicodeScalars {
        let addition = CharacterSet.controlCharacters.contains(scalar) ? " " : String(scalar)
        if bytes + addition.utf8.count > maxStringBytes { truncated = true; break }
        result += addition
        bytes += addition.utf8.count
    }
    return result
}

func finish() -> Never {
    report["truncated"] = truncated
    // UTF-8 and JSON escaping can expand strings; enforce the final byte bound.
    while true {
        let data = try? JSONSerialization.data(withJSONObject: report,
                                                options: [.sortedKeys])
        if let data, data.count + 1 <= maxOutputBytes {
            FileHandle.standardOutput.write(data)
            FileHandle.standardOutput.write(Data([10]))
            exit(0)
        }
        report["truncated"] = true
        var reduced = false
        for key in ["observedRoots", "windows"] {
            var roots = report[key] as? [[String: Any]] ?? []
            if let index = roots.lastIndex(where: {
                !($0["controls"] as? [[String: Any]] ?? []).isEmpty
            }) {
                var controls = roots[index]["controls"] as? [[String: Any]] ?? []
                controls.removeLast()
                roots[index]["controls"] = controls
                reduced = true
            } else if !roots.isEmpty {
                roots.removeLast()
                reduced = true
            }
            report[key] = roots
            if reduced { break }
        }
        if !reduced {
            // A fixed, non-sensitive fallback if serialization itself failed.
            print("{\"schema\":1,\"platform\":\"darwin\",\"status\":\"error\",\"errors\":[\"serialization_failed\"]}")
            exit(0)
        }
    }
}

func checkBudget() throws {
    if ProcessInfo.processInfo.systemUptime >= deadline {
        truncated = true
        throw ProbeError(message: "traversal_deadline")
    }
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
          info.pbi_uid == getuid() else {
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
    return Identity(executable: actualExecutable,
                    startSeconds: info.pbi_start_tvsec,
                    startMicroseconds: info.pbi_start_tvusec)
}

func attribute(_ element: AXUIElement, _ name: CFString) throws -> CFTypeRef? {
    try checkBudget()
    var value: CFTypeRef?
    let result = AXUIElementCopyAttributeValue(element, name, &value)
    if result == .success { return value }
    if result == .attributeUnsupported || result == .noValue { return nil }
    throw ProbeError(message: "ax_attribute_error_\(result.rawValue)")
}

func elements(_ element: AXUIElement, _ name: CFString, cap: Int) throws -> [AXUIElement] {
    try checkBudget()
    var count: CFIndex = 0
    let countResult = AXUIElementGetAttributeValueCount(element, name, &count)
    if countResult == .attributeUnsupported || countResult == .noValue { return [] }
    if countResult == .notImplemented {
        throw ProbeError(message: "ax_not_implemented", status: "unsupported")
    }
    if countResult == .apiDisabled {
        throw ProbeError(message: "ax_api_disabled", status: "untrusted")
    }
    guard countResult == .success else {
        throw ProbeError(message: "ax_children_error_\(countResult.rawValue)")
    }
    if count > cap { truncated = true }
    if count == 0 || cap == 0 { return [] }
    try checkBudget()
    var values: CFArray?
    let result = AXUIElementCopyAttributeValues(element, name, 0, min(count, cap), &values)
    guard result == .success else { throw ProbeError(message: "ax_children_error_\(result.rawValue)") }
    return (values as? [AXUIElement]) ?? []
}

func snapshot(_ element: AXUIElement, pid: pid_t, depth: Int) throws -> [String: Any]? {
    try checkBudget()
    guard visited < maxNodes else { truncated = true; return nil }
    visited += 1
    var actualPID: pid_t = 0
    guard AXUIElementGetPid(element, &actualPID) == .success, actualPID == pid else {
        return nil // Never inspect titles or children belonging to another PID.
    }
    _ = AXUIElementSetMessagingTimeout(element, 0.15)
    return ["role": bounded(try attribute(element, kAXRoleAttribute as CFString) as? String ?? ""),
            "title": bounded(try attribute(element, kAXTitleAttribute as CFString) as? String ?? ""),
            "enabled": (try attribute(element, kAXEnabledAttribute as CFString) as? NSNumber)?.boolValue ?? NSNull(),
            "depth": depth]
}

do {
    var options: [String: String] = [:]
    var index = 1
    while index < CommandLine.arguments.count {
        let key = CommandLine.arguments[index]
        guard ["--pid", "--profile", "--executable"].contains(key),
              options[key] == nil, index + 1 < CommandLine.arguments.count else {
            throw ProbeError(message: "invalid_arguments")
        }
        options[key] = CommandLine.arguments[index + 1]
        index += 2
    }
    let environment = ProcessInfo.processInfo.environment
    guard let pid = Int32(options["--pid"] ?? environment["AA_STORE_PID"] ?? ""), pid > 1 else {
        throw ProbeError(message: "invalid_pid")
    }
    let profile = try canonical(options["--profile"] ?? environment["AA_STORE_PROFILE"] ?? "", directory: true)
    let executable = try canonical(options["--executable"] ?? environment["AA_STORE_EXECUTABLE"] ?? "", directory: false)
    let original = try identity(pid, profile: profile, executable: executable)
    report["identity"] = ["verified": true, "pid": pid, "profile": profile,
                          "executable": executable, "startSeconds": original.startSeconds,
                          "startMicroseconds": original.startMicroseconds]

    let trusted = AXIsProcessTrustedWithOptions([
        kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: false
    ] as CFDictionary)
    report["accessibility"] = ["trusted": trusted, "available": false,
                               "applicationAccessible": false, "nativeWindowAvailable": false,
                               "visibleNativeWindowAvailable": false]
    if !trusted { report["status"] = "untrusted"; finish() }

    let application = AXUIElementCreateApplication(pid)
    _ = AXUIElementSetMessagingTimeout(application, 0.15)
    let applicationRecord = try snapshot(application, pid: pid, depth: 0)
    report["application"] = applicationRecord ?? [:]
    let ownedWindows = try elements(application, kAXWindowsAttribute as CFString, cap: maxWindows)
    let applicationHidden = NSRunningApplication(processIdentifier: pid)?.isHidden
    let applicationAccessible = applicationRecord?["role"] as? String == "AXApplication"
    var accessibility: [String: Any] = [
        "trusted": true, "available": applicationAccessible,
        "applicationAccessible": applicationAccessible, "nativeWindowAvailable": false,
        "visibleNativeWindowAvailable": false,
        "applicationHidden": (applicationHidden as Any?) ?? NSNull()
    ]
    report["accessibility"] = accessibility
    var windows: [[String: Any]] = []
    var observations: [[String: Any]] = []
    var candidates: [(AXUIElement, [String: Any])] = []
    for window in ownedWindows {
        guard var record = try snapshot(window, pid: pid, depth: 0) else { continue }
        let isNativeWindow = record["role"] as? String == "AXWindow"
        record["windowRoleVerified"] = isNativeWindow
        if isNativeWindow {
            record["minimized"] = (try attribute(window, kAXMinimizedAttribute as CFString) as? NSNumber)?.boolValue ?? NSNull()
        }
        candidates.append((window, record))
    }
    // A non-window root cannot consume the traversal budget ahead of real windows.
    candidates.sort { ($0.1["windowRoleVerified"] as? Bool == true) && ($1.1["windowRoleVerified"] as? Bool != true) }
    for (window, candidate) in candidates {
        var record = candidate
        var controls: [[String: Any]] = []
        var queue: [(AXUIElement, Int)] = [(window, 0)]
        var cursor = 0
        do {
            while cursor < queue.count && visited < maxNodes {
                let (parent, depth) = queue[cursor]
                cursor += 1
                if depth >= maxDepth { truncated = true; continue }
                let children = try elements(parent, kAXChildrenAttribute as CFString,
                                            cap: maxNodes - visited)
                for child in children {
                    guard let childRecord = try snapshot(child, pid: pid, depth: depth + 1) else { continue }
                    controls.append(childRecord)
                    queue.append((child, depth + 1))
                }
            }
            if cursor < queue.count { truncated = true }
        } catch {
            report["errors"] = [bounded((error as? ProbeError)?.message ?? "ax_traversal_error")]
            truncated = true
        }
        record["controls"] = controls
        if record["windowRoleVerified"] as? Bool == true { windows.append(record) }
        else { observations.append(record) }
        report["windows"] = windows
        report["observedRoots"] = observations
        if ProcessInfo.processInfo.systemUptime >= deadline || visited >= maxNodes { break }
    }
    do {
        guard try identity(pid, profile: profile, executable: executable) == original else {
            throw ProbeError(message: "process_identity_changed_during_probe")
        }
    } catch {
        report["identity"] = ["verified": false, "pid": pid]
        report["windows"] = [[String: Any]]()
        report["observedRoots"] = [[String: Any]]()
        report.removeValue(forKey: "application")
        throw ProbeError(message: "process_identity_unavailable_or_changed_during_probe")
    }
    report["visitedNodes"] = visited
    let visible = applicationHidden == false && windows.contains {
        ($0["windowRoleVerified"] as? Bool) == true && ($0["minimized"] as? Bool) == false
    }
    accessibility["nativeWindowAvailable"] = !windows.isEmpty
    accessibility["visibleNativeWindowAvailable"] = visible
    accessibility["available"] = applicationAccessible || !windows.isEmpty
    report["accessibility"] = accessibility
    report["status"] = visible ? "ready" : "unsupported"
    if !visible { report["errors"] = ["no_owned_visible_accessible_window"] }
} catch {
    report["status"] = (error as? ProbeError)?.status ?? "error"
    report["errors"] = [bounded((error as? ProbeError)?.message ?? "unexpected_probe_error")]
}
finish()
