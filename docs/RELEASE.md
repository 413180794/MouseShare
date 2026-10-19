MouseShare v0.7.1 · 修复 Linux 文件粘贴后跨屏卡住 / Fix Linux handoff after file paste

- 修正 Linux/X11 自动文件粘贴与远端按键释放并发时的死锁。GUI 粘贴与输入线程统一按「输入状态锁 → X11 连接锁」获取资源，保持输入处理继续运行。
- Windows、Mac 与 Linux 的模拟复制／粘贴组合键以完整操作串行执行，避免远端修饰键释放插入组合键中间。
- 新增可稳定复现旧锁序的复制／粘贴并发测试；原生 X11 验证收到文件后自动 Ctrl+V 确实送达目标窗口，随后能返回并再次跨屏。分别覆盖 Ubuntu 本机控制与接收 Windows 控制两种状态。
- 保持已有配对、布局与内容共享设置。Ubuntu 更新后请完全退出旧进程再打开新版；卡住时可在终端执行 `pkill -x MouseShare` 后重新启动。

Fixes a Linux/X11 deadlock when automatic file paste overlaps remote key release. Clipboard and input operations now acquire injection state before the X11 connection. Synthetic copy/paste chords are serialized as a complete operation on all three platforms.

Regression tests force the original lock conflict for copy and paste. Isolated native X11 tests cover a completed file-receive callback, delivery of Ctrl+V to the focused window, return to local control and another handoff, in both local and receiving states. Existing pairing, layout and preferences are preserved. After upgrading Ubuntu, fully quit the old process and reopen the app. If it is stuck, run `pkill -x MouseShare` in a terminal, then launch the updated app.

Preview packages: Windows x64 Setup/portable ZIP, macOS arm64/Intel DMGs, Linux x64/ARM64 DEB/portable archives. Linux input requires X11. The original physical Ubuntu setup still needs user confirmation. No commercial code signature or Apple notarization. Verify SHA256SUMS.txt.
