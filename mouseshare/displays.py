"""Physical displays in a computer's native, possibly negative, coordinate space."""
import math


def union(monitors):
    left = min(m['x'] for m in monitors)
    top = min(m['y'] for m in monitors)
    return (left, top, max(m['x']+m['w'] for m in monitors)-left,
            max(m['y']+m['h'] for m in monitors)-top)


def validate_screen(value):
    if not isinstance(value, dict):
        return {}
    if any(type(value.get(k)) is not int or not 64 <= value[k] <= 32768 for k in ('w', 'h')):
        return {}
    result = dict(w=value['w'], h=value['h'], x=value.get('x', 0), y=value.get('y', 0))
    if any(type(result[k]) is not int or not -32768 <= result[k] <= 32768 for k in ('x', 'y')):
        return {}
    monitors = value.get('monitors', [])
    if not isinstance(monitors, list) or len(monitors) > 16:
        return {}
    clean, ids = [], set()
    for monitor in monitors:
        if not isinstance(monitor, dict):
            return {}
        ident = monitor.get('id')
        if not isinstance(ident, str) or not 1 <= len(ident) <= 128 or ident in ids:
            return {}
        ids.add(ident)
        if any(type(monitor.get(k)) is not int for k in ('x', 'y', 'w', 'h')):
            return {}
        x, y, w, h = (monitor[k] for k in ('x', 'y', 'w', 'h'))
        if not (64 <= w <= 32768 and 64 <= h <= 32768 and result['x'] <= x
                and result['y'] <= y and x+w <= result['x']+result['w'] and y+h <= result['y']+result['h']):
            return {}
        clean.append(dict(id=ident, x=x, y=y, w=w, h=h, primary=monitor.get('primary') is True))
    if clean:
        result['monitors'] = clean
    return result


def rectangles(screen):
    return screen.get('monitors') or [dict(x=screen.get('x', 0), y=screen.get('y', 0),
                                          w=screen.get('w', 1920), h=screen.get('h', 1080))]


def project(point, screen):
    """Nearest actual pixel; never leave a remote cursor in a desktop's empty gap."""
    x, y = point
    candidates = [(max(m['x'], min(m['x']+m['w']-1, x)), max(m['y'], min(m['y']+m['h']-1, y)))
                  for m in rectangles(screen)]
    return min(candidates, key=lambda p: (p[0]-x)**2+(p[1]-y)**2)


def normalized(point, screen):
    return [(point[0]-screen.get('x', 0))/max(1, screen['w']-1),
            (point[1]-screen.get('y', 0))/max(1, screen['h']-1)]


def native(point, screen):
    return project((screen.get('x', 0)+point[0]*(screen['w']-1),
                    screen.get('y', 0)+point[1]*(screen['h']-1)), screen)


def valid_point(point):
    return (isinstance(point, list) and len(point) == 2
            and all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1 for v in point))


def mapped_monitors(node, screen):
    for monitor in rectangles(screen):
        yield dict(x=node['x']+(monitor['x']-screen.get('x', 0))*node['w']/screen['w'],
                   y=node['y']+(monitor['y']-screen.get('y', 0))*node['h']/screen['h'],
                   w=monitor['w']*node['w']/screen['w'], h=monitor['h']*node['h']/screen['h'])


def crossing(nodes, screens, source, side, point):
    """Route between exposed physical edges, returning a native target entry point."""
    if source not in nodes or source not in screens or not valid_point(point):
        return None
    node = nodes[source]
    source_screen = screens[source]
    sx = node['x']+point[0]*(source_screen['w']-1)*node['w']/source_screen['w']
    sy = node['y']+point[1]*(source_screen['h']-1)*node['h']/source_screen['h']
    hits = []
    for a in mapped_monitors(node, screens[source]):
        edge = {'left': a['x'], 'right': a['x']+a['w'], 'top': a['y'], 'bottom': a['y']+a['h']}[side]
        axis, transverse = (sx, sy) if side in {'left', 'right'} else (sy, sx)
        start, length = (a['y'], a['h']) if side in {'left', 'right'} else (a['x'], a['w'])
        if abs(axis-edge) > 2 or not start <= transverse <= start+length:
            continue
        for key, target in nodes.items():
            if key == source:
                continue
            screen = screens.get(key, dict(w=1920, h=1080))
            for b in mapped_monitors(target, screen):
                other = {'left': b['x']+b['w'], 'right': b['x'], 'top': b['y']+b['h'], 'bottom': b['y']}[side]
                bs, bl = (b['y'], b['h']) if side in {'left', 'right'} else (b['x'], b['w'])
                if abs(edge-other) > 1 or min(start+length, bs+bl)-max(start, bs) < 8 or not bs <= transverse < bs+bl:
                    continue
                px, py = (other, transverse) if side in {'left', 'right'} else (transverse, other)
                tx = screen.get('x', 0)+(px-target['x'])*screen['w']/target['w']
                ty = screen.get('y', 0)+(py-target['y'])*screen['h']/target['h']
                tx += {'left': -9, 'right': 8}.get(side, 0)
                ty += {'top': -9, 'bottom': 8}.get(side, 0)
                entry = normalized(project((tx, ty), screen), screen)
                ratio = entry[1] if side in {'left', 'right'} else entry[0]
                hits.append((key, ratio, entry))
    unique = {key: (key, ratio, entry) for key, ratio, entry in hits}
    return next(iter(unique.values())) if len(unique) == 1 else None
