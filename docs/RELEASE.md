MouseShare v0.5.1 · 可拖动多机布局、光标识别与按需文件粘贴 / Multi-computer layout and file paste

- 修复三机共享时的文件选择：A 控制 C、B 刚复制新文件时，C 粘贴最新收到的文件信息，保留单次请求和原窗口校验。
- 新增「屏幕布局」：拖动屏幕、边缘吸附、错位与大小调整、精确坐标；最多 8 台电脑。布局同步到参与布局的已配对新版本设备。
- 可从 A→B→C 连续切换，再沿布局返回。仅从实际接触、重叠且在线的边缘跨屏；每两台需要直接控制或传文件的电脑均需独立配对。
- Windows 源端也会隐藏光标；Mac 保留经过实机验收的固定交接位置和光标窗口方案。返回、暂停、游戏模式和断线时恢复光标。接收端可显示青绿／蓝／紫／橙色光圈。
- 文件剪贴板改为按需传输：复制时只共享文件信息，在目标窗口粘贴时取回文件。Ctrl+Alt+Shift+C／V 为专用快捷键；Mac 对应 Control+Option+Shift+C／V。可选支持系统 Ctrl+V／⌘V。
- 本机发起的单次粘贴请求可自动接收对应文件。自动粘贴检查焦点窗口、输入活动、控制会话和剪贴板；变化时保留文件供手动复制。文件发送可选择具体电脑，保留显式接收、拖入／拖出及 SHA-256 校验。

The v0.5.1 patch selects the most recently received file offer across connected computers, including when a different computer supplies physical input. Drag computer rectangles to arrange up to eight paired computers. Input can travel A→B→C and back along touching edges. The source pointer hides while forwarding; the receiver can show a configurable colored ring. Files are fetched on paste, with dedicated Ctrl+Alt+Shift+C/V (Control+Option+Shift on Mac) and optional native paste shortcuts. A local one-time request authorizes its matching transfer; automatic paste requires the original window, activity, clipboard and control context to remain unchanged.

多机布局及按需文件粘贴要求参与设备升级至 v0.5.0+。基础双机键鼠／内容共享兼容旧版。每个电脑矩形代表该设备的主显示器；单机多显示器独立拓扑继续列为后续功能。Wayland 保留文件传输与手动剪贴板入口；完整键鼠与全局快捷键使用 X11。Linux 暂无实体电脑验收，CI 使用隔离 Xvfb。实体键鼠、具体文件管理器和前后台光标行为需要设备验收。

Preview builds have no commercial signing / Apple notarization. Verify `SHA256SUMS.txt` and follow the installation instructions.
