"""Curated runtime executable names. Match foreground basenames, never launchers."""
CATALOG_VERSION = 1
LEGACY_DEFAULTS = ['League of Legends.exe', 'VALORANT-Win64-Shipping.exe', 'cs2.exe']
# Runtime names can vary by channel/version. Keep this explicit and user-editable.
GAMES = (
    ('三角洲行动 / Delta Force', ('DeltaForceClient-Win64-Shipping.exe',)),
    ('英雄联盟 / League of Legends · 云顶之弈 / TFT', ('League of Legends.exe',)),
    ('无畏契约 / VALORANT', ('VALORANT-Win64-Shipping.exe',)),
    ('Counter-Strike 2', ('cs2.exe',)),
    ('Dota 2', ('dota2.exe',)),
    ('PUBG: BATTLEGROUNDS', ('TslGame.exe',)),
    ('Apex Legends', ('r5apex.exe', 'r5apex_dx12.exe')),
    ('Fortnite', ('FortniteClient-Win64-Shipping.exe',)),
    ('守望先锋 / Overwatch', ('Overwatch.exe',)),
    ('Rainbow Six Siege', ('RainbowSix.exe', 'RainbowSix_DX12.exe', 'RainbowSix_Vulkan.exe')),
    ('Call of Duty', ('cod.exe',)),
    ('永劫无间 / NARAKA: BLADEPOINT', ('NarakaBladepoint.exe',)),
    ('原神 / Genshin Impact', ('YuanShen.exe', 'GenshinImpact.exe')),
    ('崩坏：星穹铁道 / Honkai: Star Rail', ('StarRail.exe',)),
    ('绝区零 / Zenless Zone Zero', ('ZenlessZoneZero.exe',)),
    ('漫威争锋 / Marvel Rivals', ('Marvel-Win64-Shipping.exe',)),
    ('Rust', ('RustClient.exe',)),
    ('Grand Theft Auto V', ('GTA5.exe', 'GTA5_Enhanced.exe')),
    ('魔兽世界 / World of Warcraft', ('Wow.exe', 'WowClassic.exe')),
    ('黑神话：悟空 / Black Myth: Wukong', ('b1-Win64-Shipping.exe',)),
    ('HELLDIVERS 2', ('helldivers2.exe',)),
    ('幻兽帕鲁 / Palworld', ('Palworld-Win64-Shipping.exe', 'Palworld-WinGDK-Shipping.exe')),
    ("博德之门 3 / Baldur's Gate 3", ('bg3.exe', 'bg3_dx11.exe')),
    ('Cyberpunk 2077', ('Cyberpunk2077.exe',)),
    ('Warframe', ('Warframe.x64.exe',)),
    ('Destiny 2', ('destiny2.exe',)),
    ('Stardew Valley', ('Stardew Valley.exe',)),
    ('最终幻想 XIV / FINAL FANTASY XIV', ('ffxiv.exe', 'ffxiv_dx11.exe')),
    ('艾尔登法环 / ELDEN RING', ('eldenring.exe',)),
    ('Deadlock', ('deadlock.exe',)),
    ('ARC Raiders', ('PioneerGame.exe',)),
    ('战地 6 / Battlefield 6', ('bf6.exe',)),
)
DEFAULT_PROCESSES = tuple(process for _, processes in GAMES for process in processes)


def add_defaults(processes):
    result = list(processes)
    seen = {item.casefold() for item in result}
    for process in DEFAULT_PROCESSES:
        if process.casefold() not in seen:
            result.append(process)
            seen.add(process.casefold())
    return result


def upgrade_defaults(values):
    current = values.get('game_processes')
    if (isinstance(current, list) and all(isinstance(p, str) for p in current)
            and {p.casefold() for p in current} == {p.casefold() for p in LEGACY_DEFAULTS}):
        values['game_processes'] = list(DEFAULT_PROCESSES)
        values['game_catalog_version'] = CATALOG_VERSION
