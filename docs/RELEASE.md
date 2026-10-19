MouseShare v0.7.2 · 修复间歇性边缘切换 / Reliable edge re-entry

- 修复到达共享边缘后按键或点击取消停留计时，继续推同一边缘却无法重新触发的问题。
- 返回本机后的防回弹只要求离开刚才的交接边缘；沿未连接的屏幕顶部／底部移动也可重新准备切换。
- Mac 本机控制时按系统真实状态恢复漏掉的松开事件，保留实际按住的按键／鼠标键，以及接收端输入状态。输入监听中断计数可用于诊断。
- 增加可选本机诊断：`MouseShare --diagnostics`，运行中的实例也可启用。本地 input-health.json 记录状态、阻塞原因、数量、超时次数与最近状态切换，不记录键值、指针轨迹、剪贴板内容或对端标识；默认关闭。

Fixes an interrupted edge dwell that failed to restart when continuing to push the same edge. Re-entry after a return checks the actual handoff edge, so movement along an unconnected top or bottom border can rearm normally.

On macOS, locally owned input recovers missed key/button releases from native state while preserving genuinely held input and receiver state. Optional `MouseShare --diagnostics` enables a local input-health.json with blocker categories, counts, timeouts and recent state transitions. It excludes key values, pointer paths, clipboard contents and peer identifiers; diagnostics are off by default.

Preview packages: Windows x64 Setup/portable ZIP, macOS arm64/Intel DMGs, Linux x64/ARM64 DEB/portable archives. Linux input requires X11. Physical repeated handoff acceptance remains separate from automated tests. No commercial code signature or Apple notarization. Verify SHA256SUMS.txt.
