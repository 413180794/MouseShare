"""Shared desktop rectangles and edge intersections, independent of pixels and GUI."""
import math
import re
from dataclasses import dataclass

MAX_DEVICES = 8
ID = re.compile(r'[0-9a-f]{64}\Z')


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float

    @classmethod
    def parse(cls, value):
        if not isinstance(value, dict) or set(value) != {'x', 'y', 'w', 'h'}:
            raise ValueError('屏幕矩形格式无效')
        if not all(type(v) in (int, float) and math.isfinite(v) for v in value.values()):
            raise ValueError('屏幕坐标无效')
        rect = cls(**value)
        if not (-8192 <= rect.x <= 8192 and -8192 <= rect.y <= 8192
                and 64 <= rect.w <= 4096 and 64 <= rect.h <= 4096):
            raise ValueError('屏幕坐标或大小超出范围')
        return rect

    def data(self):
        return {key: round(getattr(self, key), 2) for key in ('x', 'y', 'w', 'h')}

    def overlaps(self, other):
        return min(self.x+self.w, other.x+other.w)-max(self.x, other.x) > 0.1 and min(
            self.y+self.h, other.y+other.h)-max(self.y, other.y) > 0.1


def validate_layout(value):
    if not isinstance(value, dict) or type(value.get('enabled')) is not bool:
        raise ValueError('布局格式无效')
    if type(value.get('revision')) is not int or not 0 <= value['revision'] < 2**53:
        raise ValueError('布局版本无效')
    if not isinstance(value.get('author'), str) or not ID.fullmatch(value['author']):
        raise ValueError('布局作者无效')
    nodes = value.get('nodes')
    if not isinstance(nodes, dict) or not 1 <= len(nodes) <= MAX_DEVICES:
        raise ValueError('布局最多支持八台电脑')
    excluded = value.get('excluded', [])
    if (not isinstance(excluded, list) or len(excluded) > 64
            or any(not isinstance(key, str) or not ID.fullmatch(key) or key in nodes for key in excluded)):
        raise ValueError('布局排除设备无效')
    rects = {}
    for key, node in nodes.items():
        if not isinstance(key, str) or not ID.fullmatch(key):
            raise ValueError('设备标识无效')
        rects[key] = Rect.parse(node)
    for index, a in enumerate(rects.values()):
        if any(a.overlaps(b) for b in list(rects.values())[index+1:]):
            raise ValueError('屏幕发生重叠，请将边缘对齐后保存')
    return dict(enabled=value['enabled'], revision=value['revision'], author=value['author'],
                nodes={key: rect.data() for key, rect in rects.items()}, excluded=excluded)


def neighbor(nodes, source, side, ratio):
    """Return (device, target-edge ratio) at the exact overlapping edge segment."""
    if source not in nodes:
        return None
    a = Rect.parse(nodes[source])
    coordinate = (a.y + ratio*a.h) if side in {'left', 'right'} else (a.x + ratio*a.w)
    hits = []
    for key, value in nodes.items():
        if key == source:
            continue
        b = Rect.parse(value)
        touching = {'right': abs(a.x+a.w-b.x), 'left': abs(a.x-b.x-b.w),
                    'bottom': abs(a.y+a.h-b.y), 'top': abs(a.y-b.y-b.h)}[side] <= 1
        start, length = (b.y, b.h) if side in {'left', 'right'} else (b.x, b.w)
        overlap = min(a.y+a.h, b.y+b.h)-max(a.y, b.y) if side in {'left', 'right'} else min(
            a.x+a.w, b.x+b.w)-max(a.x, b.x)
        if touching and overlap >= 8 and start <= coordinate < start+length:
            hits.append((key, max(0, min(1, (coordinate-start)/length))))
    # Corner ambiguity never silently switches to an arbitrary device.
    return hits[0] if len(hits) == 1 else None


def default_nodes(local_id, peer_ids, side='right', screens=None):
    screens = screens or {}
    local_width, local_height = screens.get(local_id, (1920, 1080))
    local_w = max(100, min(720, 180*local_width/max(1, local_height)))
    nodes = {local_id: Rect(0, 0, local_w, 180).data()}
    horizontal = 0
    for index, peer in enumerate(peer_ids):
        width, height = screens.get(peer, (1920, 1080))
        w = max(100, min(720, 180*width/max(1, height)))
        x, y = {'right': (local_w, index*180), 'left': (-w, index*180),
                'top': (horizontal, -180), 'bottom': (horizontal, 180)}[side]
        nodes[peer] = Rect(x, y, w, 180).data()
        horizontal += w
    return nodes


def layout_key(layout):
    return layout.get('revision', 0), layout.get('author', '')
