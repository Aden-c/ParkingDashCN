"""估算译文在文字框中的行数（按引擎规则：零宽空格处折行，字号按 H 高度×1.666 归一）"""
import struct, sys
from strings_tool import add_breaks

def load(path):
    b = open(path, 'rb').read(); n, asc, desc, gap = struct.unpack_from('<4H', b, 4)
    recs = {r[0]: r for r in (struct.unpack_from('<I5hI', b, 12 + i * 18) for i in range(n))}
    return recs, asc, desc, gap

def layout(font, text, size, w):
    recs, asc, desc, gap = font
    s = size / (-recs[ord('H')][3] * 1.666)
    adv = lambda ch: recs.get(ord(ch), recs[ord('H')])[5] * s
    lines = []
    for para in add_breaks(text).replace('<br>', '\n').split('\n'):
        cur = 0.0; n = 1
        for word in para.split(' '):
            ww = sum(adv(c) for c in word)
            if cur and cur + ww > w:
                n += 1; cur = 0.0
            cur += ww
        lines.append(n)
    lh = (asc + desc + gap) * s if asc else size * 1.2
    return sum(lines), sum(lines) * lh
