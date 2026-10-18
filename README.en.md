# MouseShare

[简体中文](README.md) · [English](README.en.md)

Share a keyboard, mouse, clipboard and files between **Windows, macOS and Linux (X11)** over your LAN. Move to the configured screen edge, pause briefly, and control the other computer. Move back through the opposite edge to return.

[Download](https://github.com/413180794/MouseShare/releases) · [Builds](https://github.com/413180794/MouseShare/actions) · [Acceptance checklist](docs/ACCEPTANCE.md)

**v0.4.0 is a preview.** Automated tests cover authenticated TLS peers and ownership recovery. Real desktop interaction, OS permissions and individual games require acceptance on your devices. Linux is tested with isolated Xvfb displays; no physical Linux computer was available. The application UI is currently primarily Simplified Chinese.

![Connection UI with isolated sample devices](docs/screenshot.png)

## Install

| Platform | Package | Installation |
| --- | --- | --- |
| Windows 10/11 x64 | `MouseShare-0.4.0-Windows-x64-Setup.exe` | Run Setup; retain private-LAN firewall rules |
| Windows portable | `MouseShare-0.4.0-Windows-x64-portable.zip` | Extract everything and run `MouseShare.exe` |
| Apple Silicon, macOS 13+ | `MouseShare-0.4.0-macOS-arm64.dmg` | Drag the app into Applications |
| Intel, macOS 13+ | `MouseShare-0.4.0-macOS-x86_64.dmg` | Drag the app into Applications |
| Linux x64, Ubuntu 22.04+ / Debian 12+ | `MouseShare-0.4.0-Linux-x64.deb` or `.tar.gz` | `sudo apt install ./package.deb`; or extract the portable archive |
| Linux ARM64, Ubuntu 24.04+ / Debian 13+ | `MouseShare-0.4.0-Linux-arm64.deb` or `.tar.gz` | Same as above |

Packages include Python and Qt. Linux still requires X11/Qt system libraries; the DEB declares these dependencies. The portable archive includes a user-level `install.sh` that adds a menu entry and preserves older version directories. See [Linux instructions](docs/INSTALL-Linux.txt).

Releases currently have no commercial code signing or Apple notarization. Verify the source and `SHA256SUMS.txt`. Use `Get-FileHash -Algorithm SHA256` on Windows or `shasum -a 256` on macOS. Windows SmartScreen may show an unknown publisher; macOS may require Open Anyway in System Settings → Privacy & Security. Keep system security features enabled.

### macOS permissions

The first launch opens a guide when permissions are missing. Open it later from **系统权限** (System Permissions). Each step requests its corresponding native permission, opens the correct settings page, and checks the status when you return:

1. **Accessibility** allows MouseShare to control the keyboard and mouse.
2. **Input Monitoring** allows it to read physical input for forwarding.
3. Allow **Local Network** when prompted, and allow inbound connections if your Mac firewall requires it.

Enable MouseShare in System Settings → Privacy & Security. Use `+` to add `/Applications/MouseShare.app` if missing. Complete OS authentication yourself, and quit/reopen if macOS asks. Replacing an ad hoc signed preview may require refreshing these grants.

![Permission guide with sample states](docs/permissions.png)

### Linux sessions

Full input sharing requires an **X11/Xorg** session and runs as the logged-in desktop user. Root access, membership in the `input` group and `xhost` changes are unnecessary. Linux uses XInput2 raw events, XTEST injection and active grabs to keep the source cursor at its handoff position.

On **Wayland**, this release offers file transfer and foreground clipboard buttons: **同步当前剪贴板** (Send current clipboard) and **应用收到的剪贴板** (Apply received clipboard). For full keyboard/mouse sharing, log out and choose Ubuntu on Xorg or Plasma (X11) in your login session menu. Native Wayland input portals remain future work.

## Pair your computers

1. Connect both computers to the same trusted LAN and start MouseShare.
2. On **设备连接** (Devices), select the nearby computer and choose Pair and Connect. Discovery uses multicast and broadcast.
3. **Compare the six-digit code on both computers and approve on both.** Only approve connections you intended. The certificate fingerprint is remembered for reconnection.
4. On **共享设置** (Sharing Settings), choose the other computer's relative position on each machine. For a Mac to the right of a Windows PC, select Right on Windows and Left on Mac, then save.
5. Move to the configured primary-screen edge and wait 180 ms by default. Keyboard, clicks, scrolling and dragging follow the pointer. Move outward through the entry edge to return.

If discovery is unavailable, expand Connect by IP and enter the other computer's IPv4 address. Allow **UDP 24871 and TCP 24872** on your trusted LAN. The Windows installer offers inbound rules restricted to the local subnet on private networks. Guest Wi-Fi isolation, VPNs, different subnets and firewalls can affect discovery.

## Game mode and recovery

| Action | Windows | macOS | Linux X11 |
| --- | --- | --- | --- |
| Toggle manual game mode | `Ctrl+Alt+F12` | `Control+Option+F12` (Fn may be needed) | `Ctrl+Alt+Shift+G` |
| Reclaim input immediately | `Ctrl+Alt+Esc` | `Control+Option+Esc` | `Ctrl+Alt+Shift+Esc` |

Game mode keeps physical input on this computer and pauses sharing in both directions, including clipboard/files. Manual mode persists across restarts. Controls are available in the app and tray/menu bar. Linux shortcuts avoid Ctrl+Alt+F-key virtual-terminal switching.

Windows automatically protects foreground fullscreen windows and named game executables. The defaults include Delta Force, League of Legends/TFT, VALORANT, CS2, PUBG, Apex, Fortnite, Overwatch, NARAKA, Genshin Impact, Honkai: Star Rail, Zenless Zone Zero, Marvel Rivals, Black Myth: Wukong, ARC Raiders, Battlefield 6 and more. See the [complete editable catalog](docs/GAMES.md).

The original three-entry stock list upgrades automatically. Custom lists are preserved; **补齐热门游戏名单** adds missing popular defaults without deleting your entries. Save to apply. Names are exact foreground executable basenames, matched case-insensitively. Launchers and generic Java processes are excluded.

Fullscreen videos also trigger fullscreen protection. You can disable that option while retaining game-process detection. macOS and Linux currently offer manual game mode. If an automatic condition remains active, turning off manual mode keeps protection enabled and shows the reason. Individual anticheat systems and games still require device testing.

Physical input on a receiving computer reclaims control. Holding a key or mouse button prevents accidental edge switching. Disconnect or heartbeat timeout releases remote held inputs after about 3.5 seconds.

## Clipboard and files

New text, HTML and images copied after connection sync automatically on Windows/macOS/X11. Copying files/folders starts a transfer request. Accept on the receiving computer, then paste locally; the completed record also offers Copy Files and a drag-out button. You can drop files onto the app or an optional screen-edge drop tab.

Transfers show progress, speed and estimated time, support cancellation/re-send, and save batches in separate folders to preserve existing filenames. Each file is verified with SHA-256. The default receive directory is `Downloads/MouseShare`; it is configurable. The latest 20 completed/failed records store metadata locally. Clearing records keeps received files.

- File batches: up to **100 GiB / 4096 entries**.
- Text and HTML combined: **2 MiB**. Entire clipboard payload: **8 MiB**. Images: **16 million pixels**.
- Clipboard content from before connection stays local; copy again to send. Received content is marked to avoid loops. Marked private password-manager formats are skipped; ordinary text follows your sharing settings.
- Game mode, pause, lock and disconnect stop sharing. Incomplete file transfers are cleaned up. Re-send starts from the beginning.
- Native continuous file dragging across screen edges remains future work. The current flow uses a drop tab, transfer, then local drag-out.
- Content sharing is compatible with v0.3.0+; Linux requires v0.4.0+. Wayland uses explicit foreground clipboard actions, and received files are copied through the record's Copy Files button.

![File sharing UI with sample transfer data](docs/sharing.png)

## Everyday use and limits

Closing the window keeps the app in the tray/menu bar where available. Login startup is opt-in. Edge dwell is adjustable from 100–1500 ms and receiver speed from 0.25–4×.

Physical keyboard positions use USB HID IDs; the receiver's layout and IME produce text. The Windows key maps to macOS Command, Ctrl to Control. Enable Swap Ctrl and Command/Win on the receiver to change this behavior. On X11, the standard evdev/XKB keycode layout is used; relative mice and standard wheels are covered. Tablets, custom keycode maps and specific gaming drivers need acceptance.

Each instance currently connects to one peer and uses its primary monitor as the sharing boundary. Multi-monitor topology, continuous native cross-computer file dragging, resumable transfers, video streaming and Windows ARM packages remain future work. Login/lock screens, UAC secure desktops, macOS Secure Input and elevated target applications can restrict injection. See [Microsoft's SendInput restrictions](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput).

## Local data and security

Input, clipboard and files use TLS 1.2+. Each device generates a P-256 certificate/key. Pairing commits to challenges before revealing them, proves key possession, and derives the code you compare. Future connections pin the exact certificate fingerprint. Data channels require the same peer to have an active authenticated control connection and reuse the existing TCP port. Discovery only locates addresses.

There is no cloud relay or account service. Key contents are not written to logs/configuration. LAN devices can see broadcast device names and addresses. The protocol has not had an independent security audit; use a trusted network and reject unexpected pairing requests.

| System | Data directory |
| --- | --- |
| Windows | `%LOCALAPPDATA%\MouseShare` |
| macOS | `~/Library/Application Support/MouseShare` |
| Linux | `${XDG_CONFIG_HOME:-~/.config}/MouseShare` |

Protect settings, transfer metadata, certificates and private keys. Uninstalling preserves data and received files. To fully reset, disable login startup, quit, then remove the data directory. macOS login startup uses `~/Library/LaunchAgents/io.github.makesail.mouseshare.plist`; Linux uses `${XDG_CONFIG_HOME:-~/.config}/autostart/mouseshare.desktop`.

## Development

Use Python 3.13 for release builds. Dependencies are pinned; native input runs off the GUI thread.

```sh
python3.13 -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows: .venv\Scripts\Activate.ps1
python -m pip install ".[dev]"
python -m pytest -q
python -m ruff check .
python -m mouseshare --smoke-test
python -m mouseshare
python scripts/build.py
```

`--demo` starts the UI without input/network; `--minimized` starts in the tray. Use the packaged Mac app for system authorization; Python/terminal development may receive separate grants.

Build on the target OS/architecture. Windows needs Inno Setup 6, macOS needs command-line tools and `iconutil`, and Linux needs `dpkg-deb` plus X11/Qt libraries. GitHub Actions builds five targets, tests packages and installers, and runs Linux input checks in isolated Xvfb displays. Releases include SHA-256 checksums.

`engine.py` manages ownership/recovery; `network.py` manages discovery/TLS; `security.py` handles pairing; `input/` contains Win32/Quartz/XInput2 backends; `app.py` provides the UI.

MIT. See [THIRD_PARTY.md](THIRD_PARTY.md) and the packaged `licenses` directory for dependencies.
