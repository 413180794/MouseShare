import json

from mouseshare.config import Settings
from mouseshare.games import DEFAULT_PROCESSES, GAMES, LEGACY_DEFAULTS, add_defaults


def test_common_games_defaults_are_unique_specific_runtime_basenames(tmp_path):
    assert len(GAMES) >= 25
    names = Settings(tmp_path).get('game_processes')
    assert 'DeltaForceClient-Win64-Shipping.exe' in names
    assert 'TslGame.exe' in names and 'VALORANT-Win64-Shipping.exe' in names
    assert len(names) == len({name.casefold() for name in names})
    assert all(name.endswith('.exe') and '/' not in name and '\\' not in name for name in names)
    assert not {'steam.exe', 'epicgameslauncher.exe', 'javaw.exe', 'riotclientservices.exe'} & {n.casefold() for n in names}


def test_upgrade_stock_defaults_preserves_pairing_and_game_mode(tmp_path):
    before = dict(game_processes=LEGACY_DEFAULTS, peers={'trusted': {'host': '192.168.1.20'}},
                  game_mode=True, side='left')
    (tmp_path / 'settings.json').write_text(json.dumps(before))
    settings = Settings(tmp_path)
    assert settings.get('game_processes') == list(DEFAULT_PROCESSES)
    assert settings.get('peers') == before['peers']
    assert settings.get('game_mode') and settings.get('side') == 'left'


def test_custom_list_is_preserved_and_defaults_can_be_added_idempotently(tmp_path):
    custom = ['My Game.exe', 'CS2.EXE']
    (tmp_path / 'settings.json').write_text(json.dumps(dict(game_processes=custom)))
    settings = Settings(tmp_path)
    assert settings.get('game_processes') == custom
    merged = add_defaults(custom)
    assert merged[:2] == custom and merged.count('cs2.exe') == 0
    assert 'DeltaForceClient-Win64-Shipping.exe' in merged
    assert add_defaults(merged) == merged


def test_delta_force_triggers_foreground_game_protection_without_fullscreen(tmp_path):
    from mouseshare.engine import Engine
    from mouseshare.input.base import NullBackend
    settings = Settings(tmp_path)
    engine = Engine(settings, clock=lambda: 100)
    engine.backend = NullBackend(lambda event: True)
    engine.backend.running = True
    engine.backend.foreground = lambda: ('deltaforceclient-win64-shipping.EXE', False)
    engine.tick()
    assert engine.game and 'deltaforce' in engine.auto_reason.casefold()
    engine.backend.foreground = lambda: ('steam.exe', False)
    engine.last_auto = 0
    engine.tick()
    assert not engine.game
