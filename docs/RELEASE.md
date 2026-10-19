MouseShare v0.7.3 · 碰边立即跨屏 / Instant edge switching

- 移除源端停留计时、返回等待与交接后的定时冷却；鼠标朝相接边缘向外移动时立即发起交接，键盘随之切换。
- 取消必须先向屏幕内回退的门槛。已读取现场：Mac 的 move-inward 条件阻挡切换，Windows 的 edge-dwell 状态反复被中断；两端没有交接超时。
- 防回弹改用移动方向、控制权世代标记和重复路由去重：丢弃交接前积压的旧移动，保留真实新输入和按住键／鼠标保护。
- 删除边缘停留设置，中英文界面和安装说明同步更新。已有 dwell_ms 设置保留为兼容数据，执行时忽略。

Removes source dwell, return delay and timed cooldown. An outward move at a connected edge starts handoff immediately in both directions. The mandatory move-inward gate is also removed.

Bounce prevention uses movement direction, ownership epochs and edge-route deduplication. Motion queued before ownership changes is discarded. Fresh physical input, held-key/button protection, game mode and explicit reclaim remain supported. The edge-delay setting is removed and bilingual instructions are updated. Legacy dwell_ms preferences are retained as inert compatibility data.

Preview packages: Windows x64 Setup/portable ZIP, macOS arm64/Intel DMGs, Linux x64/ARM64 DEB/portable archives. Linux input requires X11. Physical repeated handoff acceptance remains separate from automated tests. No commercial code signature or Apple notarization. Verify SHA256SUMS.txt.
