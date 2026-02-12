# Understanding Hidden Windows

When you run `wingather --show-hidden`, you'll see windows that are normally invisible. This can look alarming — dozens of windows with unfamiliar names, blank content, or cryptic titles. **This is normal.** The vast majority of hidden windows are standard operating system and application internals that run in the background on every Windows machine.

This guide explains what these windows are, why they exist, and which ones (if any) deserve attention.

## Why Do Hidden Windows Exist?

Windows applications communicate with each other and with the operating system through *message windows* — invisible windows that receive and dispatch messages. This is a fundamental part of the Win32 architecture. An application that needs to:

- Respond to clipboard changes
- Receive drag-and-drop events
- Listen for hardware notifications
- Communicate with other processes
- Render graphics offscreen

...will create one or more hidden windows to handle these tasks. These windows have no visible UI because they're not meant for human interaction — they're plumbing.

A typical desktop with a browser, terminal, GPU drivers, and a few utilities will have **50-100+ hidden windows**. A heavily-loaded developer workstation can have 150+.

## Common Hidden Window Types

### Inter-Process Communication (IPC)

| Window Title / Class | Typical Process | Purpose |
|---|---|---|
| **DDE Server Window** | Various | Dynamic Data Exchange — a legacy protocol for apps to share data. Still used by Windows shell, Office, and some tools. |
| **OLE Main Thread Wnd** | Various | Object Linking and Embedding — COM/OLE communication channel. |
| **Hidden Window** | Various | Generic message-only window for IPC. The name literally means "this window is supposed to be hidden." |

**Verdict:** Completely normal. Every Windows system has these.

### .NET and Runtime Windows

| Window Title / Class | Typical Process | Purpose |
|---|---|---|
| **.NET-BroadcastEventWindow** | .NET apps | Receives system broadcast messages (theme changes, display settings, power events) for .NET applications. The hex suffix is a unique identifier. |
| **SystemResourceNotifyWindow** | .NET apps | Monitors system resource changes (memory pressure, etc.) on behalf of .NET runtime. |
| **MediaContextNotificationWindow** | WPF apps | WPF media rendering pipeline coordination. |

**Verdict:** Standard .NET runtime infrastructure. One per .NET application is typical.

### GPU and Graphics

| Window Title / Class | Typical Process | Purpose |
|---|---|---|
| **GDI+ Window** | Various | GDI+ rendering surface. Created by any app using GDI+ for drawing (icons, images, custom UI). Multiple per application is normal. |
| **EVR Fullscreen Window** | Media apps | Enhanced Video Renderer surface. Created by apps with video playback capability even if no video is playing. |
| **NvContainerWindowClass** | nvcontainer.exe | NVIDIA driver container — manages GPU settings, telemetry, and driver services. Multiple instances are normal. |
| **NvSvc** / **UxdService** | NVDisplay.Container | NVIDIA display service windows for driver communication. |
| **BroadcastListenerWindow** | nvcontainer.exe | NVIDIA containers listening for system broadcast messages. Having 6-8 of these is typical. |
| **SmartDC** / **AMD EEU Client** | atieclxx.exe | AMD display driver service windows (equivalent to NVIDIA's containers). |

**Verdict:** Normal GPU driver infrastructure. NVIDIA systems commonly have 8-12 hidden windows from `nvcontainer.exe` alone.

### Windows Shell (explorer.exe)

| Window Title / Class | Typical Process | Purpose |
|---|---|---|
| **Task Switching** | explorer.exe | The Alt+Tab window switcher UI surface (hidden until invoked). |
| **System tray overflow window** | explorer.exe | The "show hidden icons" popup area in the system tray. |
| **Battery Meter** | explorer.exe | Battery status flyout (present even on desktops without batteries). |
| **BluetoothNotificationAreaIconWindowClass** | explorer.exe | Bluetooth tray icon handler. |
| **MiracastConnectionWindow** | explorer.exe | Wireless display connection handler. |
| **MS_WebcheckMonitor** | explorer.exe | Legacy web content monitoring (Active Desktop era, still present). |
| **EXPLORER** | explorer.exe | Shell's own internal coordination window. |

**Verdict:** Core shell infrastructure. These are present on every Windows installation.

### System Services

| Window Title / Class | Typical Process | Purpose |
|---|---|---|
| **Windows Push Notifications Platform** | svchost.exe | WNS notification delivery infrastructure. |
| **SecurityHealthSystray** | SecurityHealthSystray.exe | Windows Security (Defender) tray icon handler. |
| **Task Host Window** | taskhostw.exe | Scheduled task execution host. |
| **DWM Notification Window** | dwm.exe | Desktop Window Manager internal notification channel. |
| **CrossDeviceResumeWindow** | CrossDeviceResume.exe | Windows cross-device handoff feature (Phone Link, etc.). |

**Verdict:** Windows services. These should always be present and are not suspicious.

### Application Tray Icons and Notifications

| Window Title / Class | Typical Process | Purpose |
|---|---|---|
| **QTrayIconMessageWindow** | Qt-based apps | Message pump for Qt framework system tray icons. Every Qt app with a tray icon creates one. |
| **SwiftpointNotificationWindow** | Swiftpoint software | Peripheral device notification handler. |
| **AcrobatTrayIcon** | acrotray.exe | Adobe Acrobat tray icon message handler. |
| **ESET Proxy** | eguiProxy.exe | ESET antivirus tray communication window. |
| **Microsoft OneNote - Windows taskbar** | ONENOTEM.EXE | OneNote quick-launch tray handler. |
| **OfficePowerManagerWindow** | SDXHelper.exe | Microsoft Office power management handler. |

**Verdict:** Normal application infrastructure. Each tray icon you see typically has a hidden message window behind it.

### Terminal and IDE Windows

| Window Title / Class | Typical Process | Purpose |
|---|---|---|
| **PopupHost** | WindowsTerminal.exe | Popup/autocomplete overlay windows. Windows Terminal creates several for each tab. Multiple PopupHost windows per terminal instance is normal. |
| **Windows Terminal** | WindowsTerminal.exe | Internal coordination window (separate from the visible terminal). |

**Verdict:** Normal. Windows Terminal is especially prolific with hidden windows — 4-6 per tab is typical.

### Input and Peripheral Devices

| Window Title / Class | Typical Process | Purpose |
|---|---|---|
| **Cursor Hider** / **Cursor Exclaimer** | InputDirector, etc. | KVM/input sharing software cursor management. |
| **Input Director Info Window** | InputDirector.exe | Status/coordination for multi-computer input sharing. |
| **InputDirectorClipboardClientWindow** | InputDirector.exe | Cross-machine clipboard sync handler. |

**Verdict:** Normal for KVM/input sharing setups.

### Creative and Productivity Software

| Window Title / Class | Typical Process | Purpose |
|---|---|---|
| **CCDHiddenWindow** | Creative Cloud.exe | Adobe Creative Cloud background service window. |
| **AXWIN Frame Window** | Adobe Desktop Service | Adobe licensing/update coordination. |
| **AdobeCollabSynchronizerNotification** | AdobeCollabSync.exe | Adobe cloud collaboration sync handler. |
| **dopus.desktopdblclk** | dopusrt.exe | Directory Opus desktop double-click handler. |

**Verdict:** Normal application background services.

## When Should You Be Concerned?

Most hidden windows are benign. However, `--show-hidden` can occasionally surface windows worth investigating:

**Potentially interesting:**
- A hidden window from a process you don't recognize
- A hidden window with an unusually large size (e.g., full-screen 3840x2160) from an unexpected process
- Hidden windows from processes that shouldn't be running

**Almost certainly fine:**
- Any window type listed in the tables above
- Windows with 0x0 or 1x1 dimensions (message-only windows)
- Windows with system-infrastructure titles (DDE, GDI+, .NET-Broadcast, etc.)
- Multiple identical windows from the same process (normal for containers and frameworks)

wingather's concern scoring system already flags windows that exhibit suspicious characteristics (off-screen positioning, unusual sizing, dialog classes). Hidden windows that are also flagged with a concern level deserve the most attention.

## Using --undo

If `--show-hidden` reveals windows you'd rather not see, use `--undo` to re-hide them:

```bash
# Reveal hidden windows (state is automatically saved)
wingather --show-hidden

# Re-hide everything that was just revealed
wingather --undo
```

The undo validates that each window still belongs to the same process before hiding it, so it won't accidentally hide a different window that reused the same handle.

**Recommended workflow:**
1. Run `wingather --show-hidden --dry-run` first to preview what would be revealed
2. Review the list — most entries will be the types described above
3. If you proceed with `wingather --show-hidden`, the state is saved automatically
4. Use `wingather --undo` if you want to restore the previous state

## Further Reading

- [Win32 Message-Only Windows](https://learn.microsoft.com/en-us/windows/win32/winmsg/window-features#message-only-windows) — Microsoft's documentation on hidden message windows
- [DDE Protocol](https://learn.microsoft.com/en-us/windows/win32/dataxchg/about-dynamic-data-exchange) — Why DDE Server Windows exist
- [GDI+ Architecture](https://learn.microsoft.com/en-us/windows/win32/gdiplus/-gdiplus-gdi-start) — Graphics rendering surfaces
