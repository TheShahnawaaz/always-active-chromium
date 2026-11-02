// Test-only native uBOL actions. The separate store-ui.swift remains read-only.
// Compile with xcrun swiftc -O tests/ui/store-action.swift -o OWN_OUTPUT/store-action.
// No positive invocation is authorized until the controller/helper are reviewed.
import Foundation
import ApplicationServices
import AppKit
import Darwin

let targetName = "uBlock Origin Lite"
let targetID = "ddkjiahejlhfcafbddmgiahcphecmpfh"
let expectedPermission = "Read and change all your data on all websites"
let deadline = ProcessInfo.processInfo.systemUptime + 10
let maxNodes = 192
let maxDepth = 16
var visitedNodes = 0
var receipt: [String: Any] = [
    "schema": 1, "platform": "darwin", "status": "refused", "target": "ubol",
    "operation": "unknown", "actionAttempted": false, "actionPerformed": false,
    "actionOutcomeUncertain": false, "nativeUiAccessed": false,
    "identity": ["verified": false, "immediatelyRevalidated": false],
    "prompt": [String: Any](), "errors": [String](),
    "limits": ["totalMs": 10000, "maxNodes": maxNodes, "maxDepth": maxDepth,
               "maxWindows": 8, "maxWindowChildren": 32, "maxOutputBytes": 65536]
]

struct Refusal: Error { let code: String }
func refuse(_ code: String) throws -> Never { throw Refusal(code: code) }
func budget() throws {
    if ProcessInfo.processInfo.systemUptime >= deadline { try refuse("action_budget_exceeded") }
}
func normalized(_ value: String) -> String {
    value.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
}
func canonical(_ value: String, directory: Bool) throws -> String {
    guard value.hasPrefix("/"), value.utf8.count <= 4096, !value.utf8.contains(0) else { try refuse("absolute_path_required") }
    let result = URL(fileURLWithPath: value).resolvingSymlinksInPath().standardizedFileURL.path
    var isDirectory: ObjCBool = false
    guard FileManager.default.fileExists(atPath: result, isDirectory: &isDirectory),
          isDirectory.boolValue == directory else { try refuse("path_type_mismatch") }
    return result
}

struct ProcessIdentity: Equatable {
    let pid: pid_t
    let executable: String
    let profile: String
    let seconds: UInt64
    let microseconds: UInt64
    let started: String
    var json: [String: Any] {
        ["pid": pid, "executable": executable, "profile": profile,
         "startSeconds": seconds, "startMicroseconds": microseconds,
         "started": started, "verified": true, "immediatelyRevalidated": false]
    }
}

func processStartText(_ pid: pid_t) throws -> String {
    try budget()
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/bin/ps")
    process.arguments = ["-p", String(pid), "-o", "lstart="]
    let output = Pipe()
    process.standardOutput = output
    process.standardError = FileHandle.nullDevice
    try process.run()
    let until = min(deadline, ProcessInfo.processInfo.systemUptime + 1)
    while process.isRunning && ProcessInfo.processInfo.systemUptime < until { usleep(1000) }
    if process.isRunning { process.terminate(); try refuse("native_start_text_timeout") }
    let data = output.fileHandleForReading.readDataToEndOfFile()
    guard process.terminationStatus == 0, data.count <= 256,
          let value = String(data: data, encoding: .utf8) else { try refuse("native_start_text_unavailable") }
    return normalized(value)
}

func identity(pid: pid_t, executable: String, profile: String,
              seconds: UInt64, microseconds: UInt64, started: String) throws -> ProcessIdentity {
    try budget()
    var info = proc_bsdinfo()
    let size = MemoryLayout<proc_bsdinfo>.size
    guard proc_pidinfo(pid, PROC_PIDTBSDINFO, 0, &info, Int32(size)) == size,
          info.pbi_uid == getuid() else { try refuse("owned_process_missing_or_owner_mismatch") }
    guard info.pbi_start_tvsec == seconds, info.pbi_start_tvusec == microseconds else { try refuse("native_creation_identity_mismatch") }
    var pathBuffer = [CChar](repeating: 0, count: Int(MAXPATHLEN) * 4)
    guard proc_pidpath(pid, &pathBuffer, UInt32(pathBuffer.count)) > 0,
          try canonical(String(cString: pathBuffer), directory: false) == executable else { try refuse("owned_executable_mismatch") }
    var mib: [Int32] = [CTL_KERN, KERN_PROCARGS2, pid]
    var bytes = 0
    guard sysctl(&mib, u_int(mib.count), nil, &bytes, nil, 0) == 0,
          bytes >= 4, bytes <= 262144 else { try refuse("owned_arguments_unavailable") }
    var buffer = [UInt8](repeating: 0, count: bytes)
    guard sysctl(&mib, u_int(mib.count), &buffer, &bytes, nil, 0) == 0 else { try refuse("owned_arguments_unavailable") }
    buffer = Array(buffer.prefix(bytes))
    let argc = buffer.prefix(4).withUnsafeBytes { $0.loadUnaligned(as: Int32.self) }
    guard argc > 0, argc <= 4096 else { try refuse("owned_argument_count_invalid") }
    var offset = 4
    while offset < buffer.count && buffer[offset] != 0 { offset += 1 }
    while offset < buffer.count && buffer[offset] == 0 { offset += 1 }
    var arguments: [String] = []
    for _ in 0..<argc {
        let start = offset
        while offset < buffer.count && buffer[offset] != 0 { offset += 1 }
        guard offset < buffer.count, let value = String(bytes: buffer[start..<offset], encoding: .utf8) else { try refuse("owned_arguments_invalid") }
        arguments.append(value); offset += 1
    }
    var profiles: [String] = []
    for (index, argument) in arguments.enumerated() {
        if argument.hasPrefix("--user-data-dir=") { profiles.append(String(argument.dropFirst("--user-data-dir=".count))) }
        else if argument == "--user-data-dir", index + 1 < arguments.count { profiles.append(arguments[index + 1]) }
    }
    guard profiles.count == 1, try canonical(profiles[0], directory: true) == profile else { try refuse("owned_profile_mismatch") }
    guard try processStartText(pid) == started else { try refuse("launch_start_text_mismatch") }
    return ProcessIdentity(pid: pid, executable: executable, profile: profile,
                           seconds: seconds, microseconds: microseconds, started: started)
}

func own(_ element: AXUIElement, pid: pid_t) throws {
    try budget()
    var actual: pid_t = 0
    guard AXUIElementGetPid(element, &actual) == .success, actual == pid else { try refuse("foreign_native_element") }
    _ = AXUIElementSetMessagingTimeout(element, 0.15)
}
func attribute(_ element: AXUIElement, _ name: CFString, pid: pid_t) throws -> CFTypeRef? {
    try own(element, pid: pid)
    var value: CFTypeRef?
    let result = AXUIElementCopyAttributeValue(element, name, &value)
    if result == .success { return value }
    if result == .attributeUnsupported || result == .noValue { return nil }
    try refuse("native_attribute_unavailable_\(result.rawValue)")
}
func text(_ element: AXUIElement, _ name: CFString, pid: pid_t) throws -> String {
    guard let value = try attribute(element, name, pid: pid) as? String else { return "" }
    guard value.utf8.count <= 2048 else { try refuse("native_text_limit_exceeded") }
    return normalized(value)
}
func role(_ element: AXUIElement, pid: pid_t) throws -> String {
    try text(element, kAXRoleAttribute as CFString, pid: pid)
}
func strings(_ element: AXUIElement, pid: pid_t) throws -> [String] {
    var values: [String] = []
    for key in [kAXTitleAttribute, kAXDescriptionAttribute, kAXValueAttribute] {
        let value = try text(element, key as CFString, pid: pid)
        if !value.isEmpty { values.append(value) }
    }
    return values
}
func enabled(_ element: AXUIElement, pid: pid_t) throws -> Bool {
    (try attribute(element, kAXEnabledAttribute as CFString, pid: pid) as? NSNumber)?.boolValue == true
}
func children(_ element: AXUIElement, key: CFString = kAXChildrenAttribute as CFString,
              cap: Int, pid: pid_t) throws -> [AXUIElement] {
    try own(element, pid: pid)
    var count: CFIndex = 0
    let status = AXUIElementGetAttributeValueCount(element, key, &count)
    if status == .attributeUnsupported || status == .noValue { return [] }
    guard status == .success, count >= 0, count <= cap else { try refuse("native_tree_incomplete_or_oversized") }
    if count == 0 { return [] }
    var values: CFArray?
    guard AXUIElementCopyAttributeValues(element, key, 0, count, &values) == .success,
          let elements = values as? [AXUIElement], elements.count == count else { try refuse("native_tree_unavailable") }
    for child in elements { try own(child, pid: pid) }
    return elements
}
func activeVisible(_ window: AXUIElement, pid: pid_t) throws {
    guard NSRunningApplication(processIdentifier: pid)?.isActive == true,
          NSRunningApplication(processIdentifier: pid)?.isHidden == false,
          try role(window, pid: pid) == "AXWindow",
          (try attribute(window, kAXMinimizedAttribute as CFString, pid: pid) as? NSNumber)?.boolValue == false else { try refuse("owned_native_window_not_known_visible") }
}

func nativeRectangle(_ element: AXUIElement, pid: pid_t, label: String,
                     optional: Bool = false) throws -> CGRect? {
    let positionValue = try attribute(element, kAXPositionAttribute as CFString, pid: pid)
    let sizeValue = try attribute(element, kAXSizeAttribute as CFString, pid: pid)
    if optional && positionValue == nil && sizeValue == nil { return nil }
    guard let positionValue, let sizeValue,
          CFGetTypeID(positionValue) == AXValueGetTypeID(),
          CFGetTypeID(sizeValue) == AXValueGetTypeID() else { try refuse("\(label)_bounds_unavailable") }
    let nativePosition = unsafeBitCast(positionValue, to: AXValue.self)
    let nativeSize = unsafeBitCast(sizeValue, to: AXValue.self)
    var position = CGPoint.zero
    var size = CGSize.zero
    guard AXValueGetType(nativePosition) == .cgPoint, AXValueGetType(nativeSize) == .cgSize,
          AXValueGetValue(nativePosition, .cgPoint, &position),
          AXValueGetValue(nativeSize, .cgSize, &size),
          position.x.isFinite, position.y.isFinite, size.width.isFinite, size.height.isFinite,
          size.width > 0, size.height > 0 else { try refuse("\(label)_bounds_invalid") }
    let rectangle = CGRect(origin: position, size: size)
    guard rectangle.maxX.isFinite, rectangle.maxY.isFinite else { try refuse("\(label)_bounds_invalid") }
    return rectangle
}

func rectangleReceipt(_ rectangle: CGRect) -> [String: Double] {
    ["x": Double(rectangle.origin.x), "y": Double(rectangle.origin.y),
     "width": Double(rectangle.width), "height": Double(rectangle.height)]
}

struct Prompt {
    let window: AXUIElement
    let sheet: AXUIElement
    let heading: AXUIElement
    let affirmative: AXUIElement
    let cancel: AXUIElement
    let permission: AXUIElement?
    let checkbox: AXUIElement?
}

func verifyButtonVisibility(_ prompt: Prompt, pid: pid_t) throws -> [String: Any] {
    try activeVisible(prompt.window, pid: pid)
    guard let window = try nativeRectangle(prompt.window, pid: pid, label: "owned_window"),
          let affirmative = try nativeRectangle(prompt.affirmative, pid: pid, label: "affirmative"),
          let cancel = try nativeRectangle(prompt.cancel, pid: pid, label: "cancel"),
          window.contains(affirmative), window.contains(cancel) else { try refuse("native_buttons_outside_owned_window") }
    let sheet = try nativeRectangle(prompt.sheet, pid: pid, label: "native_sheet", optional: true)
    if let sheet {
        guard sheet.contains(affirmative), sheet.contains(cancel) else { try refuse("native_buttons_outside_owned_sheet") }
    }
    guard try enabled(prompt.affirmative, pid: pid), try enabled(prompt.cancel, pid: pid) else { try refuse("native_buttons_no_longer_enabled") }
    var result: [String: Any] = [
        "method": "native_AXPosition_AXSize_containment",
        "owningWindow": rectangleReceipt(window),
        "affirmative": rectangleReceipt(affirmative), "cancel": rectangleReceipt(cancel),
        "insideOwningWindow": true, "sheetBoundsAvailable": sheet != nil
    ]
    if let sheet { result["sheet"] = rectangleReceipt(sheet); result["insideSheet"] = true }
    return result
}

func unchecked(_ element: AXUIElement, pid: pid_t) throws -> Bool {
    let labels = try strings(element, pid: pid)
    guard try role(element, pid: pid) == "AXCheckBox", labels.contains("Report abuse"),
          let value = try attribute(element, kAXValueAttribute as CFString, pid: pid) as? NSNumber else { try refuse("report_abuse_state_unknown_or_unexpected") }
    return value.doubleValue == 0
}

func findPrompt(_ application: AXUIElement, pid: pid_t, operation: String) throws -> Prompt {
    let heading = operation == "accept-install" ? "Add \"\(targetName)\"?" : "Remove \"\(targetName)\"?"
    let affirmativeLabel = operation == "accept-install" ? "Add extension" : "Remove"
    var matches: [Prompt] = []
    for window in try children(application, key: kAXWindowsAttribute as CFString, cap: 8, pid: pid) {
        guard try role(window, pid: pid) == "AXWindow" else { try refuse("application_root_is_not_native_window") }
        if (try attribute(window, kAXMinimizedAttribute as CFString, pid: pid) as? NSNumber)?.boolValue != false { continue }
        for sheet in try children(window, cap: 32, pid: pid) where try role(sheet, pid: pid) == "AXSheet" {
            guard try text(sheet, kAXTitleAttribute as CFString, pid: pid) == heading else { continue }
            var pending: [(AXUIElement, Int)] = [(sheet, 0)]
            var seen: [AXUIElement] = []
            var headings: [AXUIElement] = [], affirmative: [AXUIElement] = [], cancel: [AXUIElement] = []
            var permissions: [AXUIElement] = [], checkboxes: [AXUIElement] = []
            while !pending.isEmpty {
                let (element, depth) = pending.removeLast()
                if seen.contains(where: { CFEqual($0, element) }) { continue }
                seen.append(element); visitedNodes += 1
                guard visitedNodes <= maxNodes else { try refuse("native_node_limit_exceeded") }
                let elementRole = try role(element, pid: pid)
                let subrole = try text(element, kAXSubroleAttribute as CFString, pid: pid)
                guard elementRole != "AXWebArea", subrole != "AXSecureTextField" else { try refuse("web_or_password_subtree_refused") }
                let values = try strings(element, pid: pid)
                if elementRole == "AXHeading", values.contains(heading) { headings.append(element) }
                if elementRole == "AXButton", values.contains(affirmativeLabel) { affirmative.append(element) }
                if elementRole == "AXButton", values.contains("Cancel") { cancel.append(element) }
                if elementRole == "AXStaticText", values.contains(expectedPermission) { permissions.append(element) }
                if elementRole == "AXCheckBox" { checkboxes.append(element) }
                let descendants = try children(element, cap: maxNodes - visitedNodes, pid: pid)
                guard depth < maxDepth || descendants.isEmpty else { try refuse("native_sheet_depth_limit_exceeded") }
                for child in descendants { pending.append((child, depth + 1)) }
            }
            guard headings.count == 1, affirmative.count == 1, cancel.count == 1,
                  try enabled(affirmative[0], pid: pid), try enabled(cancel[0], pid: pid) else { try refuse("native_prompt_controls_missing_disabled_or_ambiguous") }
            if operation == "accept-install" {
                guard permissions.count == 1, checkboxes.isEmpty else { try refuse("install_permission_or_checkbox_mismatch") }
            } else {
                guard checkboxes.count <= 1 else { try refuse("remove_checkbox_ambiguous") }
                if let checkbox = checkboxes.first, try !unchecked(checkbox, pid: pid) { try refuse("report_abuse_must_be_unchecked") }
            }
            matches.append(Prompt(window: window, sheet: sheet, heading: headings[0],
                                  affirmative: affirmative[0], cancel: cancel[0],
                                  permission: permissions.first, checkbox: checkboxes.first))
        }
    }
    guard matches.count == 1 else { try refuse("native_target_sheet_not_unique") }
    try activeVisible(matches[0].window, pid: pid)
    return matches[0]
}

func supportsPress(_ element: AXUIElement, pid: pid_t) throws -> Bool {
    try own(element, pid: pid)
    var actions: CFArray?
    guard AXUIElementCopyActionNames(element, &actions) == .success else { return false }
    return (actions as? [String] ?? []).contains(kAXPressAction as String)
}

do {
    var options: [String: String] = [:]
    let required = ["--pid", "--profile", "--executable", "--expected-started",
                    "--expected-start-seconds", "--expected-start-microseconds", "--target", "--operation"]
    var index = 1
    while index < CommandLine.arguments.count {
        let key = CommandLine.arguments[index]
        guard required.contains(key), options[key] == nil, index + 1 < CommandLine.arguments.count else { try refuse("invalid_arguments") }
        options[key] = CommandLine.arguments[index + 1]; index += 2
    }
    if let operation = options["--operation"], operation.utf8.count <= 40 { receipt["operation"] = operation }
    guard Set(options.keys) == Set(required) else { try refuse("required_arguments_missing") }
    guard options["--target"] == "ubol" else { try refuse("unsupported_target") }
    let operation = options["--operation"]!
    guard ["accept-install", "confirm-remove"].contains(operation) else { try refuse("unsupported_operation") }
    guard let pid = Int32(options["--pid"]!), pid > 1 else { try refuse("invalid_pid") }
    receipt["identity"] = ["pid": pid, "verified": false, "immediatelyRevalidated": false]
    guard let seconds = UInt64(options["--expected-start-seconds"]!), seconds > 0,
          let microseconds = UInt64(options["--expected-start-microseconds"]!), microseconds < 1000000 else { try refuse("invalid_native_creation_identity") }
    let started = normalized(options["--expected-started"]!)
    guard !started.isEmpty, started.utf8.count <= 128 else { try refuse("invalid_launch_start_text") }
    let profile = try canonical(options["--profile"]!, directory: true)
    let executable = try canonical(options["--executable"]!, directory: false)
    let original = try identity(pid: pid, executable: executable, profile: profile,
                                seconds: seconds, microseconds: microseconds, started: started)
    receipt["identity"] = original.json
    receipt["nativeUiAccessed"] = true
    guard AXIsProcessTrustedWithOptions([kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: false] as CFDictionary) else { try refuse("accessibility_untrusted") }
    let application = AXUIElementCreateApplication(pid)
    let selected = try findPrompt(application, pid: pid, operation: operation)
    let immediate = try identity(pid: pid, executable: executable, profile: profile,
                                 seconds: seconds, microseconds: microseconds, started: started)
    guard immediate == original else { try refuse("owned_identity_changed") }
    // Full uniqueness, permission and checkbox-Off/absence validation follows
    // the potentially slow native/ps identity checks, rather than preceding them.
    let fresh = try findPrompt(application, pid: pid, operation: operation)
    guard CFEqual(selected.window, fresh.window), CFEqual(selected.sheet, fresh.sheet),
          CFEqual(selected.affirmative, fresh.affirmative), CFEqual(selected.cancel, fresh.cancel) else { try refuse("native_prompt_changed_during_validation") }
    try activeVisible(fresh.window, pid: pid)
    let expectedHeading = operation == "accept-install" ? "Add \"\(targetName)\"?" : "Remove \"\(targetName)\"?"
    let expectedAffirmative = operation == "accept-install" ? "Add extension" : "Remove"
    guard try children(application, key: kAXWindowsAttribute as CFString, cap: 8, pid: pid).contains(where: { CFEqual($0, fresh.window) }),
          try children(fresh.window, cap: 32, pid: pid).contains(where: { CFEqual($0, fresh.sheet) }),
          try role(fresh.sheet, pid: pid) == "AXSheet",
          try text(fresh.sheet, kAXTitleAttribute as CFString, pid: pid) == expectedHeading,
          try role(fresh.heading, pid: pid) == "AXHeading",
          try strings(fresh.heading, pid: pid).contains(expectedHeading),
          try role(fresh.affirmative, pid: pid) == "AXButton",
          try strings(fresh.affirmative, pid: pid).contains(expectedAffirmative),
          try role(fresh.cancel, pid: pid) == "AXButton",
          try strings(fresh.cancel, pid: pid).contains("Cancel"),
          try enabled(fresh.affirmative, pid: pid), try enabled(fresh.cancel, pid: pid),
          try supportsPress(fresh.affirmative, pid: pid) else { try refuse("native_prompt_no_longer_actionable") }
    if operation == "accept-install" {
        guard let permission = fresh.permission, try role(permission, pid: pid) == "AXStaticText",
              try strings(permission, pid: pid).contains(expectedPermission) else { try refuse("native_permission_text_changed") }
    }
    if let checkbox = fresh.checkbox, try !unchecked(checkbox, pid: pid) { try refuse("report_abuse_state_changed") }
    let visibility = try verifyButtonVisibility(fresh, pid: pid)
    var identityReceipt = immediate.json
    identityReceipt["immediatelyRevalidated"] = true
    receipt["identity"] = identityReceipt
    var promptReceipt: [String: Any] = [
        "nativeDialogVerified": true, "nativeSheetRoleVerified": true,
        "targetMatched": true, "targetID": targetID,
        "affirmativeLabel": operation == "accept-install" ? "Add extension" : "Remove",
        "affirmativeEnabled": true, "affirmativeUnique": true, "cancelEnabled": true,
        "affirmativeVisible": true, "cancelVisible": true, "visibility": visibility
    ]
    if operation == "accept-install" { promptReceipt["permissionTextMatched"] = true }
    else { promptReceipt["reportAbuseUncheckedOrAbsent"] = true }
    receipt["prompt"] = promptReceipt
    try budget()
    _ = AXUIElementSetMessagingTimeout(fresh.affirmative, 2)
    receipt["actionType"] = "AXPress"
    receipt["actionAttempted"] = true
    receipt["actionPerformed"] = NSNull()
    receipt["actionOutcomeUncertain"] = true
    let result = AXUIElementPerformAction(fresh.affirmative, kAXPressAction as CFString)
    guard result == .success else { try refuse("native_press_result_\(result.rawValue)") }
    receipt["actionPerformed"] = true
    receipt["actionOutcomeUncertain"] = false
    receipt["status"] = "acted"
} catch {
    let attempted = receipt["actionAttempted"] as? Bool == true
    receipt["status"] = attempted || !(error is Refusal) ? "error" : "refused"
    receipt["errors"] = [(error as? Refusal)?.code ?? "unexpected_native_action_error"]
    if attempted { receipt["actionPerformed"] = NSNull(); receipt["actionOutcomeUncertain"] = true }
}
receipt["visitedNodes"] = visitedNodes
if let data = try? JSONSerialization.data(withJSONObject: receipt, options: [.sortedKeys]), data.count < 65536 {
    FileHandle.standardOutput.write(data); FileHandle.standardOutput.write(Data([10]))
} else {
    let attempted = receipt["actionAttempted"] as? Bool == true
    print("{\"schema\":1,\"status\":\"error\",\"target\":\"ubol\",\"actionAttempted\":\(attempted),\"actionPerformed\":\(attempted ? "null" : "false"),\"actionOutcomeUncertain\":\(attempted),\"errors\":[\"receipt_serialization_failed\"]}")
}
