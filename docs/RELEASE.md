MouseShare v0.7.5 · 修复 Windows 碰边漏触发 / Fix missed Windows edge crossings

- 修复 Windows 返回后首次快速碰边被判为零移动、持续推动边缘也无法进入另一台电脑的问题。
- 本机控制时，使用 Raw Input 补充实际显示器边缘的向外移动；普通区域继续使用原有鼠标钩子，避免重复移动。
- 软件自身带标记的返回事件会更新坐标基准；连续零位移钩子事件不会覆盖原始鼠标的向外方向。
- 保留立即交接、正确返回位置、旧移动过滤、游戏模式及按住键鼠保护。可选本机诊断增加边缘原始移动和零位移钩子的计数，继续排除键值、指针轨迹及对端身份。

Windows now detects outward Raw Input at a physical display edge while local control is active. This fixes missed crossings after a return or when the cursor is already clamped to the edge. Tagged return events update the hook coordinate baseline, and repeated zero-displacement hook events no longer erase real outward motion. Regular local motion stays on the existing hook path.

Native callback regressions cover all four edges, immediate return/re-entry, peer recovery while staying at the edge, held-input/game protection, negative monitor coordinates, stale captured motion and tagged input filtering. These tests exercise the Windows callback entry points with simulated events; physical-device acceptance remains separate.

Preview packages: Windows x64 Setup/portable ZIP, macOS arm64/Intel DMGs, Linux x64/ARM64 DEB/portable archives. Linux input requires X11. No commercial code signature or Apple notarization. Verify SHA256SUMS.txt.
