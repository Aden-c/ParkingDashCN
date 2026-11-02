"""按文字框宽度预先断行（插入 <br>），用于漫画气泡、教程气泡

引擎自己折行时只管“放得下就放”，中文常常剩一个字单独成行；教程气泡的排版宽度
又比可见区域宽几像素，行尾的字会被裁掉一截。这里先算好行数，再把各行排得尽量一样长。

字宽模型（Parking Dash 实测）：像素 = 字宽 × 字号 × K ÷ 字形总上下范围，K ≈ 0.987
（帮助页 17 号真好体、教程 18 号、漫画 16 号快乐体三处测得 0.980~0.994）。
"""
import re
import struct

K = 0.99
TAG = re.compile(r'</?[A-Za-z]+>')
_fonts = {}


def load(path):
    if path not in _fonts:
        b = open(path, 'rb').read()
        n = struct.unpack_from('<H', b, 4)[0]
        recs = {r[0]: r for r in (struct.unpack_from('<I5hI', b, 12 + i * 18) for i in range(n))}
        top = min(r[3] for r in recs.values()); bottom = max(r[4] for r in recs.values())
        _fonts[path] = (recs, bottom - top)
    return _fonts[path]


def width(font, s, size):
    recs, ext = font
    s = TAG.sub('', s)
    return sum(recs.get(ord(c), recs[ord('H')])[5] for c in s) * size * K / ext


def _greedy(toks, ws, limit):
    lines, cur, w = [], [], 0.0
    for t, tw in zip(toks, ws):
        if cur and w + tw > limit:
            lines.append(cur); cur, w = [], 0.0
        cur.append(t); w += tw
    if cur:
        lines.append(cur)
    return lines


def balance(text, font_path, size, box_w):
    """text 是 add_breaks 处理过的串（空格 = 折行点）。返回各行用 <br> 连接的串"""
    font = load(font_path)
    out = []
    for para in text.split('<br>'):
        toks = [t for t in para.split(' ') if t]
        if not toks:
            out.append(para); continue
        ws = [width(font, t, size) for t in toks]
        n = len(_greedy(toks, ws, box_w))
        if n == 1:
            out.append(para); continue
        lo, hi = max(ws), box_w  # 二分找“行数不变时最窄的行宽”，各行就差不多一样长
        for _ in range(30):
            mid = (lo + hi) / 2
            if len(_greedy(toks, ws, mid)) <= n:
                hi = mid
            else:
                lo = mid
        out.append('<br>'.join(' '.join(line) for line in _greedy(toks, ws, hi)))
    return '<br>'.join(out)
