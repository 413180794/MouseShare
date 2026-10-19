MouseShare v0.6.2 · 柔和边缘投递 / Gentle glass edge hints

- 文件拖到已连接电脑的屏幕边缘时，在拖入点附近显示小范围毛玻璃提示；桌面其他部分保持原样。上、下、左、右均按实际屏幕布局定位。
- 约 5.6 秒一轮的柔和光晕与轻微图案漂移，投递区域和文字位置固定。Mac／Windows 的减少动态效果设置会关闭动效，收起提示后停止动画计时器。
- 提示保留目标电脑、文件信息、松手发送和 Esc 取消。松手后短暂确认，传输继续在后台进行；保持认证目标绑定、接收确认与原有文件校验。
- 中文与英文同步更新，Mac 与 Windows 使用系统原生局部模糊，其他桌面按合成器能力使用模糊或深色半透明背景。

Dragging local files to a connected screen edge now shows a compact glass hint near the entry point. The rest of the desktop stays unchanged. All four directions follow the screen layout. A slow glow and tiny icon drift animate the hint while its drop target and text remain stationary. macOS and Windows reduced-motion preferences are respected, and animation stops when hidden.

Release to send or press Esc to cancel. The original authenticated destination, receive confirmation and file integrity checks remain in place. English and Simplified Chinese are supported. Native compositor blur is used where available, with a translucent fallback; screen capture permission is unnecessary.

Preview packages: Windows x64 Setup/portable ZIP, macOS arm64/Intel DMGs, Linux x64/ARM64 DEB/portable archives. Linux input sharing requires X11; physical Linux hardware remains untested. This preview has no commercial code signature or Apple notarization. Verify SHA256SUMS.txt.
