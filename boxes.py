"""Parking Dash 各条目的显示空间（供 proofread.py 的“显示空间”列和 fitcheck 使用）

漫画文字由 scripts/comics.lua 调用 AddComicText_Aux(t, x, y, w, h, key[, size]) 添加，
字号默认 16（doncomic），居中。这里从字节码里把每次调用的常量参数取出来。
"""
import luac50
from project import game, original

COMIC_FONT_SIZE = 16
# 漫画行距 ≈ 字号 × 1.0：按结局页实机截图逐行量出（8_b/c/d/g 四个气泡误差 ≤1px）。
# 早先用的 1.15 × 1.116 偏大，多行台词会被误判为超出气泡上下边缘
COMIC_LINE = 1.0


def comic_boxes():
    """{key: (x, y, w, h, size)}；同一句台词画在几个位置时取第一个（断行用的框宽相同）"""
    out = {}
    for key, box in comic_boxes_all():
        out.setdefault(key, box)
    return out


def comic_boxes_all():
    """[(key, (x, y, w, h, size))]，按脚本顺序；同一句台词可能出现多次（如结局的“欢迎回来”画了 3 处）"""
    out = []

    def walk(f):
        regs, func = {}, None
        for i in f['code']:
            op = i & 0x3f; A = i >> 24; Bx = (i >> 6) & 0x3ffff
            if op == 5:  # GETGLOBAL
                name = f['k'][Bx]
                if isinstance(name, str) and name.startswith('AddComicText'):
                    func, regs = (A, name), {}
            elif op == 1 and func:  # LOADK
                regs[A] = f['k'][Bx]
            elif op == 29 and func and A == func[0]:  # CALL
                b = func[0]
                args = [regs.get(b + n) for n in range(2, 8)]
                if isinstance(args[4], str):
                    x, y, w, h, key, size = args
                    out.append((key, (x, y, w, h, size if isinstance(size, float) else COMIC_FONT_SIZE)))
                func = None
        for p in f['p']:
            walk(p)

    walk(luac50.load(game('scripts/comics.lua')))   # 读游戏里的（可能已被 lua_patch.py 挪过框）
    return out


COMIC_PAGES = {1: '1_1', 2: '1_2', 3: '1_3', 4: '2_1', 5: '3_1', 6: '4_1', 7: '5_1', 8: '6_1'}


def bubble_rows(key, box):
    """从漫画原图量出气泡形状：从文字框中心向外填充与中心同色的区域。
    返回 {y: (气泡左边缘 x, 右边缘 x)}；没有气泡（填出来的区域远大于文字框）返回 None"""
    import re
    import numpy as np
    from PIL import Image
    from scipy import ndimage
    x, y, w, h, size = box
    page = COMIC_PAGES[int(re.match(r'comic_(\d+)_', key).group(1))]
    full = np.asarray(Image.open(original_or_game(f'comics/comics_{page}.jpg')).convert('RGB')).astype(int)
    # 只在文字框四周的窗口里找（相邻气泡常连成一片）
    x0, y0 = max(0, int(x - w * 0.4)), max(0, int(y - h * 0.4))
    x1, y1 = min(full.shape[1], int(x + w * 1.4)), min(full.shape[0], int(y + h * 1.4))
    img = full[y0:y1, x0:x1]
    cx, cy = int(x + w / 2) - x0, int(y + h / 2) - y0
    seed = np.median(img[cy - 3:cy + 4, cx - 3:cx + 4].reshape(-1, 3), axis=0)
    same = np.abs(img - seed).sum(axis=2) < 60
    lab, _ = ndimage.label(same)
    if lab[cy, cx] == 0:
        return None
    region = lab == lab[cy, cx]
    mid = np.nonzero(region[cy])[0]
    if mid.min() == 0 and mid.max() == region.shape[1] - 1:
        return None   # 中心这一行左右都通到窗口边：不是封闭的气泡（文字直接写在画面上）
    if seed.sum() < 620:
        return None   # 气泡内部都是很亮的米白色（RGB 和约 725）；暗的是画面上的一块同色区域（如地面）
    rows = {}
    for yy in range(region.shape[0]):
        cols = np.nonzero(region[yy])[0]
        if len(cols):
            rows[yy + y0] = (cols.min() + x0, cols.max() + x0)
    return rows


def original_or_game(rel):
    import os
    p = original(rel)
    return p if os.path.exists(p) else game(rel)


TUTORIAL_SIZE = 18    # 教程气泡（exe 里定义）：真好体 18 号，截图实测
TUTORIAL_WIDTH = 330   # 最宽的教程气泡可见区约 366px，但排版宽度比可见区宽几像素，取保守值


def prebreak_targets():
    """需要预先断行的条目：{key: (字体文件, 字号, 可用宽度)}，供 strings_tool apply 使用"""
    import json
    from project import EN
    t = {}
    for k, (x, y, w, h, size) in comic_boxes().items():
        t[k] = (game('fonts/doncomic.mvec'), size, w - 6)
    for k in json.load(open(EN, encoding='utf-8')):
        if k.startswith('tutorial') and k[8:].isdigit():
            t[k] = (game('fonts/rollout.mvec'), TUTORIAL_SIZE, TUTORIAL_WIDTH)
    return t


def lua_label_boxes():
    """所有脚本里带固定 label 的文字控件：{key: (脚本名, w, h)}（w/h 由运算得出时为 None）"""
    import glob, os
    from project import BACKUP
    out = {}

    def walk(f, name):
        K, tab = f['k'], {}
        rk = lambda x: K[x - 250] if 250 <= x < 250 + len(K) else None
        for i in f['code']:
            op = i & 0x3f; C = (i >> 6) & 0x1ff; B = (i >> 15) & 0x1ff; A = i >> 24
            if op == 10:                      # NEWTABLE
                tab[A] = {}
            elif op == 9 and A in tab:        # SETTABLE
                k, v = rk(B), rk(C)
                if isinstance(k, str):
                    tab[A][k] = v
                if k == 'label' and isinstance(v, str):
                    out.setdefault(v, (name, tab[A].get('w'), tab[A].get('h')))
        for p in f['p']:
            walk(p, name)

    for path in glob.glob(os.path.join(BACKUP, 'scripts', '*.lua')):
        walk(luac50.load(path), os.path.basename(path))
    return out


# 真好体中文每字约 字号×0.86 像素；漫画快乐体因字形范围变小放大了 1.116 倍，约 字号×0.88
def _per_line(w, size, k=0.86):
    return int(w // (size * k))


def _chars(s):
    import re
    return len(re.sub(r'</?[A-Za-z]+>|\s', '', s))


def layout_issues(zh):
    """排版检查：{key: (级别, 说明)}，级别 '放不下' > '出界' > '贴边'。
    漫画用 sim_comic 按游戏规则排好后，拿笔画范围和原图里气泡的实际边缘比；帮助页按文字框高度算；开场白按行数算"""
    import re
    import prebreak, sim_comic, strings_tool
    out = {}
    R = game('fonts/rollout.mvec')
    targets = prebreak_targets()
    glyphs, ext = sim_comic.load_font(game('fonts/doncomic.mvec'))
    worst = {}   # 同一台词画在几处时，取最挤的一处
    for k, box in comic_boxes_all():
        if k not in zh:
            continue
        r, lines = sim_comic.check(k, zh, targets, glyphs, ext, box)
        if r is None:
            if sim_comic.crosses_border(k, zh, targets, glyphs, ext, box):
                out[k] = ('出界', f'文字直接写在画面上（没有气泡），压到了分格黑边，可按 Alt+Enter 分成两行或缩短（现 {_chars(zh[k])} 字）；'
                                  f'见模拟图 preview/comic_{k.split("_")[1]}.png')
            continue
        if k in worst and worst[k][0] >= r:
            continue
        worst[k] = (r, lines)
    for k, (r, lines) in worst.items():
        n, page = _chars(zh[k]), COMIC_PAGES[int(re.match(r'comic_(\d+)_', k).group(1))]
        where = f'见模拟图 preview/comic_{k.split("_")[1]}.png（原图 comics_{page}.jpg）'
        tip = '可在译文里按 Alt+Enter 自己换行，排成中间宽、上下窄的形状'
        if r >= 9:
            out[k] = ('放不下', f'{lines} 行超出气泡上下边缘，建议缩短或少分几行（现 {n} 字）；{where}')
        elif r > 1.0:
            out[k] = ('出界', f'有一行超出气泡左右边缘，{tip}，或缩短到约 {int(n / r * 0.95)} 字（现 {n} 字）；{where}')
        elif r > 0.97:
            out[k] = ('贴边', f'贴着气泡边缘，{tip}，或略缩短（现 {n} 字）；{where}')
    lb = lua_label_boxes()
    for k, v in zh.items():
        if k.startswith('help') and k in lb and lb[k][1] and lb[k][2]:
            _, w, h = lb[k]
            lines = sum(prebreak.balance(strings_tool.add_breaks(p), R, 17, w).count('<br>') + 1 for p in v.split('<br>'))
            if lines * 17 * 1.1 > h + 4:
                out[k] = ('放不下', f'文字框 {w:.0f}×{h:.0f} 约放 {int(h // (17 * 1.1))} 行，现在约 {lines} 行')
        elif k.startswith('intro_level'):
            lines = prebreak.balance(strings_tool.add_breaks(v), R, 20, 380).count('<br>') + 1
            if lines > 6:
                out[k] = ('放不下', f'开场对话框约 {lines} 行，原版最多约 6 行，建议不超过 130 字（现 {_chars(v)} 字）')
    return out


def box_sizes():
    """每个 key 的显示空间说明（翻译表/校对表的“显示空间”列）"""
    sizes, lb = {}, lua_label_boxes()
    for k, (name, w, h) in lb.items():
        if w and h:
            sizes[k] = f'文字框 {w:.0f}×{h:.0f}'
        elif w:
            sizes[k] = f'文字框宽 {w:.0f}'
    for k in list(sizes):
        if k.startswith('help') and not k.startswith(('help_page', 'help1_title', 'help2_title', 'help3_title', 'help4_title')):
            w = lb[k][1]
            if w:
                sizes[k] += f'（约每行 {_per_line(w, 17)} 字）'
    for k, (x, y, w, h, size) in comic_boxes().items():
        sizes[k] = f'气泡 {w:.0f}×{h:.0f}（约每行 {_per_line(w, size, 0.88)} 字，{max(1, int(h // (size * 1.05)))} 行）'
    from project import EN
    import json
    for k in json.load(open(EN, encoding='utf-8')):
        if k.startswith('intro_level'):
            sizes[k] = '开场对话框宽 380（约每行 22 字，建议不超过 6 行 ≈ 130 字）'
        elif k.startswith('descrlvl'):
            sizes[k] = '关卡说明框 480×100'
        elif k.startswith('decor_t'):
            sizes[k] = '装饰说明框 460×80（约 2~3 行）'
        elif k.startswith('tutorial') and k[8:].isdigit():
            sizes[k] = f'教程气泡（工具按每行约 {_per_line(TUTORIAL_WIDTH, TUTORIAL_SIZE)} 字自动断行）'
    return sizes


if __name__ == '__main__':
    for k, v in comic_boxes().items():
        print(k, v)
