MouseShare v0.7.0 · 多显示器、长按与文件粘贴 / Displays, held keys and file paste

- 读取 Windows、Mac、X11 的全部活动显示器；布局中分别显示，同一电脑按系统排列成组拖动。支持负坐标、错位、真实外侧边缘交接与返回。组内位置由系统显示设置调整；旧布局可「重置排列」并保存以采用新比例。热插拔更新显示信息并安全收回控制。
- 修复 X11 捕获时漏发长按重复事件，以及接收重复按下重置 Xorg 重复计时器的问题；Mac 注入正确标记重复。文字、退格、方向键及松开停止重复已在隔离 X11 原生环境验证。
- 增加「切换控制到此电脑」和 Ctrl+Alt+Space（Mac Control+Option+Space），方便只用笔记本内置键盘时主动切换；再按收回。Windows 缺失扫描码时使用系统映射补全。实体笔记本的原报告仍待使用者复测。
- 专用复制／粘贴改为 Ctrl+Alt+C／V（Mac Control+Option+C／V），兼容原四键组合，并保留 AltGr 输入。
- 可选预接收文件：每次最多 64 MiB，传输和 SHA-256 校验完成后写入真实系统文件剪贴板，支持右键「粘贴」。新本机剪贴板内容不会被覆盖；大文件按需接收。
- 可选文件管理器右键「接收文件到此处（MouseShare）」：Windows 11 使用「显示更多选项」；Ubuntu GNOME 需 python3-nautilus 并重新打开 Files。接收到所选目录下的独立批次文件夹，保留现有文件；菜单可关闭撤销。

All active displays are now shown and used for routing on Windows, macOS and X11. Displays belonging to one computer preserve the system arrangement and move as a group. Reset and save older layouts to adopt the new aspect ratio. Negative coordinates, offset displays, return positions and display changes are covered.

Held-key repeats now follow X11's grabbed core-key path; repeated network downs no longer reset Xorg's repeat timer. macOS receives proper autorepeat metadata. An explicit Control this computer action and Ctrl+Alt+Space switch support keyboard-only handoff. The original built-in laptop-keyboard report still needs a physical-device retest.

Copy/paste shortcuts use Ctrl+Alt+C/V (Control+Option+C/V on Mac); the original four-key combinations also work. Optional file prefetch receives up to 64 MiB per copy and fills the real system file clipboard after verification, enabling system Paste menus. New local clipboard content is preserved. Optional Explorer / GNOME Files context menus receive into a separate batch folder inside the chosen directory. Windows 11 uses Show more options; GNOME requires python3-nautilus and reopening Files.

Preview packages: Windows x64 Setup/portable ZIP, macOS arm64/Intel DMGs, Linux x64/ARM64 DEB/portable archives. Linux input requires X11. Physical Ubuntu dual-monitor/laptop acceptance remains pending. No commercial code signature or Apple notarization. Verify SHA256SUMS.txt.
