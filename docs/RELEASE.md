MouseShare v0.5.2 · 全屏毛玻璃文件投递 / Full-screen glass file drop

- 用全屏临时投递层替换常驻边缘小窗：平时隐藏，拖本地文件到布局中已连接的电脑边缘时展开，显示目标设备、文件信息和 Esc 取消提示。
- 松手提交后迅速收起，传输继续在后台进行；保留对端接收确认、目录副本和 SHA-256 校验。支持本机鼠标及远端键鼠控制中的文件拖放。
- Mac 使用系统原生模糊，Windows 11 使用 Desktop Acrylic，其他桌面按合成器能力提供模糊或深色半透明背景。尊重减少透明度设置，不需要屏幕录制权限。
- 提供 3 秒效果预览；取消、断线、游戏保护、暂停和控制会话变化时收起。投递目标绑定进入浮层时的认证连接，避免切换选中设备后发错电脑。

The persistent edge tab is replaced by a transient full-screen glass drop surface. Drag local files to a connected screen edge, check the destination, then release to send or press Esc to cancel. The desktop returns while transfer continues in the background. Local and remotely controlled file drags are supported. Native compositor blur is requested on supported desktops, with a dark translucent fallback and respect for reduced-transparency settings. No desktop screenshots or Screen Recording permission are needed.

沿用 v0.5.x 多机拖动布局、源端光标隐藏、四色接收光圈和文件复制粘贴。原生连续跨电脑拖动到任意应用仍使用“投递 → 接收 → 本机拖出”的交接方式。Linux 全局键鼠／边缘拖动使用 X11；Wayland 保留软件内文件投递和手动剪贴板入口。Windows、macOS arm64／Intel、Linux x64／ARM64 包均包含运行依赖。

预览版尚无商业代码签名或 Apple 公证。请核对 SHA256SUMS.txt；平台与实体文件管理器的拖动表现需实机验收。
