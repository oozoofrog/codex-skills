import AppKit
let folder = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
final class Recorder: NSObject {
    var count = 0
    let field = NSTextField(frame: NSRect(x: 30, y: 105, width: 320, height: 28))
    override init() { super.init(); field.placeholderString = "Background test value" }
    @objc func clicked(_ sender: NSButton) {
        count += 1
        let data: [String:Any] = ["count":count,"value":field.stringValue,"frontmost":NSWorkspace.shared.frontmostApplication?.localizedName ?? "unknown"]
        let bytes = try! JSONSerialization.data(withJSONObject:data, options:[.prettyPrinted,.sortedKeys])
        try! bytes.write(to: folder.appendingPathComponent("result.json"))
    }
}
let app = NSApplication.shared
let monitor = NSEvent.addLocalMonitorForEvents(matching:[.leftMouseDown,.leftMouseUp]) { event in
    let data:[String:Any] = ["window":event.windowNumber,"x":event.locationInWindow.x,"y":event.locationInWindow.y,"type":event.type.rawValue]
    try! JSONSerialization.data(withJSONObject:data).write(to:folder.appendingPathComponent("event.json"))
    return event
}
app.setActivationPolicy(.accessory)
let recorder = Recorder()
let window = NSWindow(contentRect: NSRect(x: 200, y: 250, width: 400, height: 200),styleMask:[.titled,.closable],backing:.buffered,defer:false)
window.title = "Jev Background Fixture"
window.contentView!.addSubview(recorder.field)
let button = NSButton(title:"Record background result", target:recorder, action:#selector(Recorder.clicked(_:)))
button.frame = NSRect(x:30,y:45,width:320,height:35)
window.contentView!.addSubview(button)
window.makeFirstResponder(recorder.field)
window.orderFrontRegardless()
app.run()
