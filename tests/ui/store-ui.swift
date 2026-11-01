// Read-only native UI prerequisite probe. Never clicks, grants access, or installs.
// Compile: xcrun swiftc -O tests/ui/store-ui.swift -o OWN_OUTPUT/store-ui
// Run: store-ui --pid PID --profile ABSOLUTE_PATH --executable ABSOLUTE_PATH
// Optional: --mode dialog captures owned focused UI; it never accepts a dialog.
import Foundation
import ApplicationServices
import AppKit
import Darwin

let maxNodes = 128
let maxDepth = 8
let maxWindows = 8
let maxStringBytes = 240
let maxOutputBytes = 65_536
let maxAncestorDepth = 16
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
        if !reduced, var inspection = report["dialogInspection"] as? [String: Any] {
            var containers = inspection["containers"] as? [[String: Any]] ?? []
            if let index = containers.lastIndex(where: {
                !($0["controls"] as? [[String: Any]] ?? []).isEmpty
            }) {
                var controls = containers[index]["controls"] as? [[String: Any]] ?? []
                controls.removeLast()
                containers[index]["controls"] = controls
                reduced = true
            } else if !containers.isEmpty {
                containers.removeLast()
                reduced = true
            } else if var ancestors = inspection["ancestors"] as? [[String: Any]], !ancestors.isEmpty {
                ancestors.removeLast()
                inspection["ancestors"] = ancestors
                reduced = true
            }
            inspection["containers"] = containers
            inspection["truncated"] = true
            report["dialogInspection"] = inspection
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

func snapshot(_ element: AXUIElement, pid: pid_t, depth: Int,
              detailed: Bool = false) throws -> [String: Any]? {
    try checkBudget()
    guard visited < maxNodes else { truncated = true; return nil }
    visited += 1
    var actualPID: pid_t = 0
    guard AXUIElementGetPid(element, &actualPID) == .success, actualPID == pid else {
        return nil // Never inspect titles or children belonging to another PID.
    }
    _ = AXUIElementSetMessagingTimeout(element, 0.15)
    var record: [String: Any] = [
        "role": bounded(try attribute(element, kAXRoleAttribute as CFString) as? String ?? ""),
        "title": bounded(try attribute(element, kAXTitleAttribute as CFString) as? String ?? ""),
        "enabled": (try attribute(element, kAXEnabledAttribute as CFString) as? NSNumber)?.boolValue ?? NSNull(),
        "depth": depth
    ]
    if detailed {
        let subrole = try attribute(element, kAXSubroleAttribute as CFString) as? String ?? ""
        record["subrole"] = bounded(subrole)
        record["description"] = bounded(try attribute(element, kAXDescriptionAttribute as CFString) as? String ?? "")
        if subrole == "AXSecureTextField" {
            record["value"] = NSNull()
            record["valueRedacted"] = true
        } else if let value = try attribute(element, kAXValueAttribute as CFString) {
            if let string = value as? String { record["value"] = bounded(string) }
            else if let number = value as? NSNumber { record["value"] = number }
            else { record["value"] = NSNull() }
        } else { record["value"] = NSNull() }
    }
    return record
}

func ownedElementAttribute(_ element: AXUIElement, _ name: CFString,
                           pid: pid_t) throws -> AXUIElement? {
    guard let value = try attribute(element, name),
          CFGetTypeID(value) == AXUIElementGetTypeID() else { return nil }
    let child = unsafeBitCast(value, to: AXUIElement.self)
    var actualPID: pid_t = 0
    guard AXUIElementGetPid(child, &actualPID) == .success, actualPID == pid else { return nil }
    _ = AXUIElementSetMessagingTimeout(child, 0.15)
    return child
}

func inspectDialog(_ application: AXUIElement, pid: pid_t) -> [String: Any] {
    var result: [String: Any] = [
        "status": "not-found", "focused": NSNull(), "ancestors": [[String: Any]](),
        "containers": [[String: Any]](), "notes": [String](),
        "promptIdentityVerified": false, "truncated": false,
        "maxAncestorDepth": maxAncestorDepth
    ]
    do {
        guard NSRunningApplication(processIdentifier: pid)?.isActive == true else {
            result["notes"] = ["owned_application_not_active"]
            return result
        }
        guard let focused = try ownedElementAttribute(application, kAXFocusedUIElementAttribute as CFString, pid: pid) else {
            result["notes"] = ["no_owned_focused_element"]
            return result
        }
        // Before reading text/value, prove every ancestor belongs to the same PID
        // and the focused subtree reaches an actual native AXWindow.
        var chain: [AXUIElement] = []
        var cursor: AXUIElement? = focused
        var windowVerified = false
        while let current = cursor, chain.count < maxAncestorDepth, visited < maxNodes {
            try checkBudget()
            if chain.contains(where: { CFEqual($0, current) }) { break }
            visited += 1
            var actualPID: pid_t = 0
            guard AXUIElementGetPid(current, &actualPID) == .success, actualPID == pid else { break }
            chain.append(current)
            if try attribute(current, kAXRoleAttribute as CFString) as? String == "AXWindow" {
                windowVerified = true
                break
            }
            cursor = try ownedElementAttribute(current, kAXParentAttribute as CFString, pid: pid)
        }
        guard windowVerified else {
            result["notes"] = ["focused_element_has_no_verified_owned_window_ancestry"]
            if chain.count >= maxAncestorDepth || visited >= maxNodes { truncated = true }
            result["truncated"] = truncated
            return result
        }
        var records: [[String: Any]] = []
        for (depth, element) in chain.enumerated() {
            guard var record = try snapshot(element, pid: pid, depth: depth, detailed: true) else { break }
            record["windowOwnershipVerified"] = true
            records.append(record)
        }
        guard records.count == chain.count, let focusRecord = records.first,
              var windowRecord = records.last else {
            throw ProbeError(message: "focused_chain_snapshot_incomplete")
        }
        windowRecord["windowRoleVerified"] = true
        windowRecord["minimized"] = (try attribute(chain.last!, kAXMinimizedAttribute as CFString) as? NSNumber)?.boolValue ?? NSNull()
        result["focused"] = focusRecord
        result["ancestors"] = Array(records.dropFirst())
        result["window"] = windowRecord
        result["status"] = "observed"
        result["notes"] = ["owned_focused_ui_only_not_a_verified_install_prompt"]

        // Prefer a semantic dialog if exposed, then nearby focused ancestors;
        // these are observation roots, not assumptions about Chrome's prompt.
        var selected: [(Int, String)] = []
        func select(_ index: Int, _ reason: String) {
            if !selected.contains(where: { $0.0 == index }) { selected.append((index, reason)) }
        }
        if let semantic = records.indices.dropFirst().first(where: {
            let role = records[$0]["role"] as? String ?? ""
            let subrole = records[$0]["subrole"] as? String ?? ""
            return ["AXDialog", "AXSheet", "AXAlert"].contains(role) ||
                ["AXDialog", "AXSystemDialog"].contains(subrole)
        }) { select(semantic, "nearest_exposed_dialog_role") }
        if chain.count > 1 { select(1, "focused_parent") }
        if chain.count > 2 { select(2, "near_focused_ancestor") }
        if chain.count > 3 { select(3, "near_focused_ancestor") }
        if selected.count < 4 { select(chain.count - 1, "verified_focused_window") }
        var containers: [[String: Any]] = []
        for (index, reason) in selected.prefix(4) {
            var record = records[index]
            record["selectionReason"] = reason
            var controls: [[String: Any]] = []
            var queue: [(AXUIElement, Int)] = [(chain[index], 0)]
            var position = 0
            do {
                while position < queue.count, visited < maxNodes {
                    let (parent, depth) = queue[position]
                    position += 1
                    if depth >= maxDepth { truncated = true; continue }
                    for child in try elements(parent, kAXChildrenAttribute as CFString, cap: maxNodes - visited) {
                        guard var childRecord = try snapshot(child, pid: pid, depth: depth + 1, detailed: true) else { continue }
                        childRecord["windowOwnershipVerified"] = true
                        controls.append(childRecord)
                        queue.append((child, depth + 1))
                    }
                }
                if position < queue.count { truncated = true }
            } catch {
                truncated = true
                result["notes"] = [bounded((error as? ProbeError)?.message ?? "dialog_traversal_error")]
            }
            record["controls"] = controls
            containers.append(record)
            result["containers"] = containers
            if visited >= maxNodes || ProcessInfo.processInfo.systemUptime >= deadline { break }
        }
    } catch {
        result["status"] = "error"
        result["notes"] = [bounded((error as? ProbeError)?.message ?? "dialog_inspection_error")]
    }
    result["truncated"] = truncated
    return result
}

do {
    var options: [String: String] = [:]
    var index = 1
    while index < CommandLine.arguments.count {
        let key = CommandLine.arguments[index]
        guard ["--pid", "--profile", "--executable", "--mode"].contains(key),
              options[key] == nil, index + 1 < CommandLine.arguments.count else {
            throw ProbeError(message: "invalid_arguments")
        }
        options[key] = CommandLine.arguments[index + 1]
        index += 2
    }
    let environment = ProcessInfo.processInfo.environment
    let mode = options["--mode"] ?? "preflight"
    guard ["preflight", "dialog"].contains(mode) else { throw ProbeError(message: "invalid_mode") }
    if mode == "dialog" { report["mode"] = mode }
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
    if mode == "dialog" { report["dialogInspection"] = inspectDialog(application, pid: pid) }
    for (window, candidate) in candidates {
        var record = candidate
        var controls: [[String: Any]] = []
        var queue: [(AXUIElement, Int)] = [(window, 0)]
        var cursor = 0
        do {
            while mode == "preflight" && cursor < queue.count && visited < maxNodes {
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
            if mode == "preflight" && cursor < queue.count { truncated = true }
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
        report.removeValue(forKey: "dialogInspection")
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
