import pytest
from mouseshare.topology import Rect, neighbor, validate_layout

A, B, C = (letter*64 for letter in 'abc')


def test_offset_edges_map_global_height_and_stop_in_uncovered_segments():
    nodes = {A: Rect(0, 0, 320, 180).data(), B: Rect(320, 90, 240, 180).data(),
             C: Rect(0, -180, 320, 180).data()}
    assert neighbor(nodes, A, 'right', .25) is None
    assert neighbor(nodes, A, 'right', .75) == (B, .25)
    assert neighbor(nodes, B, 'left', .25) == (A, .75)
    assert neighbor(nodes, A, 'top', .5) == (C, .5)
    assert neighbor(nodes, A, 'left', .5) is None


def test_shared_edge_segments_select_exact_device_without_corner_ambiguity():
    nodes = {A: Rect(0, 0, 320, 360).data(), B: Rect(320, 0, 320, 180).data(),
             C: Rect(320, 180, 320, 180).data()}
    assert neighbor(nodes, A, 'right', .25) == (B, .5)
    assert neighbor(nodes, A, 'right', .5) == (C, 0)
    assert neighbor(nodes, A, 'right', .75) == (C, .5)


@pytest.mark.parametrize('bad', [Rect(100, 0, 320, 180).data(), dict(x=float('nan'), y=0, w=320, h=180),
                                dict(x=320, y=0, w=1, h=180)])
def test_reject_overlapping_or_invalid_rectangles(bad):
    with pytest.raises(ValueError):
        validate_layout(dict(enabled=True, author=A, revision=1, nodes={A: Rect(0, 0, 320, 180).data(), B: bad}))
