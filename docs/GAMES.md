# 热门游戏默认名单 / Default game catalog


默认匹配 Windows 前台游戏的进程文件名，忽略大小写。仅监测前台进程，保留原有全屏保护。游戏渠道或版本可能更名，可在游戏页编辑；此名单代表识别规则，具体游戏环境仍需实机验收。


Windows matches the foreground executable basename, case-insensitively. Runtime names can vary by channel/version; edit the list in Game Mode. These are detection rules, not a claim that every game has been physically tested.


| 游戏 / Game | 默认进程 / Executables |
| --- | --- |
| 三角洲行动 / Delta Force | `DeltaForceClient-Win64-Shipping.exe` |
| 英雄联盟 / League of Legends · 云顶之弈 / TFT | `League of Legends.exe` |
| 无畏契约 / VALORANT | `VALORANT-Win64-Shipping.exe` |
| Counter-Strike 2 | `cs2.exe` |
| Dota 2 | `dota2.exe` |
| PUBG: BATTLEGROUNDS | `TslGame.exe` |
| Apex Legends | `r5apex.exe`, `r5apex_dx12.exe` |
| Fortnite | `FortniteClient-Win64-Shipping.exe` |
| 守望先锋 / Overwatch | `Overwatch.exe` |
| Rainbow Six Siege | `RainbowSix.exe`, `RainbowSix_DX12.exe`, `RainbowSix_Vulkan.exe` |
| Call of Duty | `cod.exe` |
| 永劫无间 / NARAKA: BLADEPOINT | `NarakaBladepoint.exe` |
| 原神 / Genshin Impact | `YuanShen.exe`, `GenshinImpact.exe` |
| 崩坏：星穹铁道 / Honkai: Star Rail | `StarRail.exe` |
| 绝区零 / Zenless Zone Zero | `ZenlessZoneZero.exe` |
| 漫威争锋 / Marvel Rivals | `Marvel-Win64-Shipping.exe` |
| Rust | `RustClient.exe` |
| Grand Theft Auto V | `GTA5.exe`, `GTA5_Enhanced.exe` |
| 魔兽世界 / World of Warcraft | `Wow.exe`, `WowClassic.exe` |
| 黑神话：悟空 / Black Myth: Wukong | `b1-Win64-Shipping.exe` |
| HELLDIVERS 2 | `helldivers2.exe` |
| 幻兽帕鲁 / Palworld | `Palworld-Win64-Shipping.exe`, `Palworld-WinGDK-Shipping.exe` |
| 博德之门 3 / Baldur's Gate 3 | `bg3.exe`, `bg3_dx11.exe` |
| Cyberpunk 2077 | `Cyberpunk2077.exe` |
| Warframe | `Warframe.x64.exe` |
| Destiny 2 | `destiny2.exe` |
| Stardew Valley | `Stardew Valley.exe` |
| 最终幻想 XIV / FINAL FANTASY XIV | `ffxiv.exe`, `ffxiv_dx11.exe` |
| 艾尔登法环 / ELDEN RING | `eldenring.exe` |
| Deadlock | `deadlock.exe` |
| ARC Raiders | `PioneerGame.exe` |
| 战地 6 / Battlefield 6 | `bf6.exe` |

旧版三项原始默认值会升级到新名单；自定义或空名单保留。「补齐热门游戏名单」追加缺少项目，保留现有内容，点击保存后生效。
The original three-entry stock list upgrades automatically. Custom/empty lists are preserved. “Add popular defaults” appends missing entries; save to apply.

Steam／Epic／Riot 启动器、通用 Java 进程不在默认规则中，避免普通桌面工作触发保护。
Launcher processes and generic Java runtimes are excluded to avoid locking normal desktop work.

核对线索 / References: [Steam popular games](https://store.steampowered.com/charts/mostplayed), [Delta Force crash analysis on Microsoft Q&A](https://learn.microsoft.com/zh-cn/answers/questions/2285370/win11-dmp), [Fortnite official support](https://www.epicgames.com/help/c-34254770/c-38015632/optimer-lav-opdateringshastighed-i-fortnite-pa-pc-a25544495), [Marvel Rivals official FAQ](https://www.marvelrivals.com/guide/20241201/41348_1197223.html), [ARC Raiders observed runtime](https://github.com/ValveSoftware/Proton/issues/9164), [Battlefield 6 support report](https://forums.ea.com/discussions/battlefield-6-technical-issues-en/game-crashing-when-joining-matches-/13282107).
