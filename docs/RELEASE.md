MouseShare v0.7.4 · 优化连续快速往返 / Faster repeated handoffs

- TLS 输入通道改为发送队列有消息立即唤醒网络线程，消除原先等待 8ms 轮询的开销；TLS 仍由单一线程读写。
- Windows 光标隐藏窗口在返回后隐藏并复用，避免每次跨屏重建；显示器布局变化时重建，空闲时停止计时器。
- 本机可选诊断增加最近 64 次交接确认耗时和待确认期间丢弃移动的数量，不记录键值、指针轨迹或对端标识。
- 保留碰边立即切换、返回位置、旧移动过滤、游戏／按住键保护与剪贴板安全规则。

The TLS input queue now wakes its I/O thread immediately instead of waiting for the polling interval. A single thread still owns TLS reads and writes. Windows reuses hidden cursor surfaces across handoffs and rebuilds them when display geometry changes. Idle surfaces stop their timer.

Optional local diagnostics include the latest 64 handoff-confirmation durations and the count of motion packets discarded while waiting for confirmation. Key values, pointer paths and peer identifiers are excluded. Instant edge switching and existing ownership, game, held-input and clipboard protections remain in place.

Preview packages: Windows x64 Setup/portable ZIP, macOS arm64/Intel DMGs, Linux x64/ARM64 DEB/portable archives. Linux input requires X11. Automated native handoff probes use simulated motion deltas through the real backend/TLS path; physical mouse feel remains a separate acceptance step. No commercial code signature or Apple notarization. Verify SHA256SUMS.txt.
