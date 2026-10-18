MouseShare v0.4.0 · Linux X11、热门游戏默认规则与双语 README / Linux X11, game defaults and bilingual documentation

- 新增 Linux X11 键鼠共享，支持 x64 与 ARM64 的 DEB／便携 tar.gz；沿用现有自动发现、加密配对、剪贴板与文件传输。
- Linux 使用原始输入、XTEST 注入与交接点限制；以普通桌面用户运行。登录启动可选，提供会话检查及 X11／Wayland 指引。
- Wayland 当前支持文件传输与前台手动剪贴板操作。完整键鼠共享使用 X11／Xorg；原生 Wayland 输入门户适配列为后续工作。
- Windows 默认加入 32 组常见游戏，包括三角洲行动、英雄联盟／云顶、无畏契约、CS2、PUBG、Apex、Fortnite、漫威争锋、黑神话：悟空、ARC Raiders、战地 6 等。旧版原始默认值自动升级，自定义名单保留，可一键补齐。
- README 提供中文和英文入口，安装、快捷键、系统权限、共享限制、游戏规则及开发流程均有说明。

Linux 恢复快捷键：Ctrl+Alt+Shift+Esc；游戏模式：Ctrl+Alt+Shift+G，避开虚拟终端按键。Windows／Mac 快捷键保持原样。

New Linux X11 support ships as DEB and portable archives for x64/ARM64. Wayland offers file transfer and explicit foreground clipboard operations; full input sharing requires X11/Xorg. The Windows defaults now include 32 common game groups and preserve custom process lists. Chinese and English READMEs cover installation, permissions, shortcuts and current limits.

Linux has no physical desktop acceptance yet; CI uses isolated Xvfb input/clipboard displays. Game rules are foreground executable detection rules; individual games and anticheat environments still need acceptance. Content sharing remains compatible with v0.3.0+ peers.

All releases remain previews without commercial signing / Apple notarization. Verify `SHA256SUMS.txt` and use the installation instructions in the repository.
