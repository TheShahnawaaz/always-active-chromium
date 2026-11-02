// CDP reports maximized/zoomed windows separately from fullscreen windows.
// Accept only a known windowed state on the exact window under test.
export function isExpectedWindowedWindow(window,expectedWindowId){
  return Number.isInteger(expectedWindowId)&&window?.windowId===expectedWindowId&&
    ['normal','maximized'].includes(window?.bounds?.windowState);
}
