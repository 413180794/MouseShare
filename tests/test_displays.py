import pytest

from mouseshare.displays import crossing, native, normalized, project, union, validate_screen
from mouseshare.topology import Rect

A, B = 'a'*64, 'b'*64


def dual():
    monitors = [dict(id='left', x=-1920, y=0, w=1920, h=1080, primary=False),
                dict(id='main', x=0, y=0, w=1920, h=1080, primary=True)]
    x, y, w, h = union(monitors)
    return dict(x=x, y=y, w=w, h=h, monitors=monitors)


def test_all_monitors_union_negative_origin_and_protocol_validation():
    screen = dual()
    assert (screen['x'], screen['w']) == (-1920, 3840)
    assert validate_screen(screen) == screen
    for change in [dict(x=False), dict(w=0), dict(monitors=[screen['monitors'][0]]*2),
                   dict(monitors=[dict(screen['monitors'][0], x=-4000)])]:
        assert not validate_screen(dict(screen, **change))
    assert validate_screen(dict(w=1920, h=1080)) == dict(x=0, y=0, w=1920, h=1080)


def test_crossing_uses_secondary_display_and_preserves_return_height():
    screens = {A: dual(), B: dict(w=1920, h=1080)}
    nodes = {A: Rect(0, 0, 640, 180).data(), B: Rect(640, 0, 320, 180).data()}
    point = normalized((1919, 700), screens[A])
    key, ratio, entry = crossing(nodes, screens, A, 'right', point)
    assert key == B and native(entry, screens[B]) == pytest.approx((8, 700))
    back = crossing(nodes, screens, B, 'left', normalized((0, 300), screens[B]))
    assert back[0] == A and native(back[2], screens[A]) == pytest.approx((1911, 300))
    # The border between a computer's own monitors remains an OS transition.
    assert crossing(nodes, screens, A, 'right', normalized((-1, 300), screens[A])) is None


def test_offset_display_gap_never_becomes_a_route_or_remote_cursor_position():
    screen = dual()
    screen['monitors'][1]['y'] = 540
    screen['h'] = 1620
    screens = {A: screen, B: dict(w=1920, h=1080)}
    nodes = {A: Rect(0, 0, 640, 270).data(), B: Rect(640, 0, 320, 180).data()}
    assert crossing(nodes, screens, A, 'right', normalized((1919, 200), screen)) is None
    hit = crossing(nodes, screens, A, 'right', normalized((1919, 700), screen))
    assert hit[0] == B
    assert native(hit[2], screens[B])[1] == pytest.approx(700, abs=2)
    assert project((100, 100), screen) == (-1, 100)
    assert project((-100, 1500), screen) == (0, 1500)
