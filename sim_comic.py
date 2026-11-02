"""模拟漫画页的中文排版（不用进游戏就能看效果）

  python sim_comic.py 8            画第 8 段漫画（comic_8_*），输出 preview/comic_8.png
  python sim_comic.py 1 --outline  同时画出每个文字框的边界

照引擎规则排：strings_tool 写入时的断行（<br> 与零宽折行点）→ 框内放不下再按折行点折行 →
水平居中、整块竖直居中。字号按“字宽 × 字号 × K ÷ 字形总上下范围”换算（见 prebreak.py）。
"""
import json, os, re, struct, sys
from PIL import Image, ImageDraw

import boxes, prebreak, strings_tool
from project import HERE, ZH, game

K_DONCOMIC = 0.98      # 漫画快乐体实测（prebreak.py 的 K 取 0.99 是保守值）
SS = 4                 # 超采样倍数
PAGES = boxes.COMIC_PAGES  # {1: '1_1', 2: '1_2', 3: '1_3', 4: '2_1', 5: '3_1', 6: '4_1', 7: '5_1', 8: '6_1'}


def load_font(path):
    b = open(path, 'rb').read()
    n = struct.unpack_from('<H', b, 4)[0]
    recs = [struct.unpack_from('<I5hI', b, 12 + i * 18) for i in range(n)]
    glyphs = {}
    for k, r in enumerate(recs):
        end = recs[k + 1][6] if k + 1 < n else len(b)
        glyphs[r[0]] = (r[1:6], b[r[6]:end])
    top = min(g[0][2] for g in glyphs.values()); bottom = max(g[0][3] for g in glyphs.values())
    return glyphs, bottom - top


def contours(data):
    i, cs, cur = 0, [], None
    while i < len(data):
        op = data[i]; i += 1
        if op == 8:
            break
        if op == 2:
            i += 1
        elif op == 4:
            cur = [struct.unpack_from('<hh', data, i)]; cs.append(cur); i += 4
        elif op == 5:
            cur.append(struct.unpack_from('<hh', data, i)); i += 4
        elif op == 6:
            cx, cy, x, y = struct.unpack_from('<hhhh', data, i); i += 8
            x0, y0 = cur[-1]
            for t in (j / 6 for j in range(1, 7)):
                cur.append(((1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t * t * x,
                            (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t * t * y))
    return cs


def draw_glyph(mask, g, x, base, s):
    """把一个字形按奇偶规则画到超采样蒙版上（x、base 为超采样坐标）"""
    (xmin, xmax, ymin, ymax, adv), data = g
    if xmax <= xmin or ymax <= ymin:
        return
    x0, y0 = int(x + xmin * s) - 2, int(base + ymin * s) - 2
    w, h = int((xmax - xmin) * s) + 5, int((ymax - ymin) * s) + 5
    acc = Image.new('1', (w, h), 0)
    for cs in contours(data):
        layer = Image.new('1', (w, h), 0)
        ImageDraw.Draw(layer).polygon([(x + p[0] * s - x0, base + p[1] * s - y0) for p in cs], fill=1)
        acc = Image.frombytes('1', (w, h), bytes(a ^ b for a, b in zip(acc.tobytes(), layer.tobytes())))
    mask.paste(1, (x0, y0), acc)


def layout(text, glyphs, s, w):
    """按 <br> 分段，段内超宽时在折行点（空格）处折行；返回各行（已去掉标签和零宽空格）"""
    adv = lambda t: sum(glyphs.get(ord(c), glyphs[ord('H')])[0][4] for c in t) * s
    lines = []
    for para in text.split('<br>'):
        para = re.sub(r'</?[A-Za-z]+>', '', para)
        cur = ''
        for tok in para.split(' '):
            if cur and adv(cur + tok) > w:
                lines.append(cur); cur = tok
            else:
                cur += tok
        lines.append(cur)
    return lines


def place(key, zh, targets, glyphs, ext, box):
    """按引擎规则排好一个文字框：返回 [(行文字, 起点 x, 基线 y, (笔画左, 右, 上, 下))]"""
    x, y, w, h, size = box
    s = size * K_DONCOMIC / ext
    lines = layout(strings_tool.render(key, zh[key], targets), glyphs, s, w)
    lh = size * boxes.COMIC_LINE
    top = y + (h - lh * len(lines)) / 2
    out = []
    for i, line in enumerate(lines):
        gs = [glyphs.get(ord(c), glyphs[ord('H')]) for c in line]
        lw = sum(g[0][4] for g in gs) * s
        x0 = x + (w - lw) / 2
        base = top + i * lh + lh * 0.8
        ink = [g for g in gs if g[0][1] > g[0][0]]
        if ink:
            left = x0 + gs[0][0][0] * s
            right = x0 + (sum(g[0][4] for g in gs[:-1]) + gs[-1][0][1]) * s
            box_ink = (left, right, base + min(g[0][2] for g in ink) * s, base + max(g[0][3] for g in ink) * s)
        else:
            box_ink = None
        out.append((line, x0, base, box_ink))
    return out


def check(key, zh, targets, glyphs, ext, box):
    """笔画和气泡边缘比较：返回 (r, 行数)。r = 最挤那一行“笔画到气泡该行中线的距离 ÷ 气泡该行半宽”，
    >1 说明笔画出了气泡（文字偏向一边也算进去）；没有气泡（文字直接写在画面上）返回 (None, 行数)"""
    rows = boxes.bubble_rows(key, box)
    placed = place(key, zh, targets, glyphs, ext, box)
    if rows is None:
        return None, len(placed)
    r = 0.0
    for _, _, _, ink in placed:
        if not ink:
            continue
        left, right, t, b = ink
        for yy in range(int(t) + 3, int(b) - 2):   # 上下留 3px 容差（竖直位置是估算的）
            if yy not in rows:
                r = 9.9
                continue
            lo, hi = rows[yy]
            mid, half = (lo + hi) / 2, (hi - lo) / 2
            r = max(r, max(mid - left, right - mid) / half if half > 0 else 9.9)
    return r, len(placed)


def crosses_border(key, zh, targets, glyphs, ext, box):
    """没有气泡、直接写在画面上的文字：笔画范围里如果有一整列（或一整行）几乎全是深色，
    说明压到了分格的黑边上"""
    import numpy as np
    page = PAGES[int(key.split('_')[1])]
    img = np.asarray(Image.open(boxes.original_or_game(f'comics/comics_{page}.jpg')).convert('L')).astype(int)
    for _, _, _, ink in place(key, zh, targets, glyphs, ext, box):
        if not ink:
            continue
        l, r, t, b = (int(v) for v in ink)
        dark = img[max(t, 0):b + 1, max(l, 0):r + 1] < 70
        if dark.size and ((dark.mean(axis=0) > 0.9).any() or (dark.mean(axis=1) > 0.9).any()):
            return True
    return False


def main():
    n = int(sys.argv[1])
    outline = '--outline' in sys.argv
    zh = json.load(open(ZH, encoding='utf-8'))
    targets = strings_tool.prebreak_targets()
    glyphs, ext = load_font(game('fonts/doncomic.mvec'))
    page = Image.open(game(f'comics/comics_{PAGES[n]}.jpg')).convert('RGB')
    W, H = page.size
    mask = Image.new('1', (W * SS, H * SS), 0)
    d = ImageDraw.Draw(page)
    for key, box in boxes.comic_boxes_all():
        if not key.startswith(f'comic_{n}_') or key not in zh:
            continue
        s = box[4] * K_DONCOMIC / ext
        for line, x0, base, _ in place(key, zh, targets, glyphs, ext, box):
            for c in line:
                g = glyphs.get(ord(c))
                if g:
                    draw_glyph(mask, g, x0 * SS, base * SS, s * SS)
                    x0 += g[0][4] * s
        if outline:
            r, _ = check(key, zh, targets, glyphs, ext, box)
            if r is None and crosses_border(key, zh, targets, glyphs, ext, box):
                r = 9.0
            x, y, w, h, _ = box
            color = (0, 160, 255) if r is None or r <= 0.97 else (255, 160, 0) if r <= 1.0 else (255, 0, 0)
            d.rectangle([x, y, x + w, y + h], outline=color, width=2 if color != (0, 160, 255) else 1)
    small = mask.convert('L').resize((W, H), Image.LANCZOS)
    page.paste((0, 0, 0), mask=small)
    os.makedirs(os.path.join(HERE, 'preview'), exist_ok=True)
    out = os.path.join(HERE, 'preview', f'comic_{n}.png')
    page.save(out)
    print(out)


if __name__ == '__main__':
    main()
