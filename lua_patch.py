"""改漫画文字框的位置 / 大小（scripts/comics.lua 里 AddComicText_Aux(t, x, y, w, h, key) 的常量参数）

  python lua_patch.py           以 backup/ 里的原版 comics.lua 为底改写，写入游戏
  python lua_patch.py restore   还原原版 comics.lua

文字在框内水平、竖直都居中，挪框就是挪字。新数值若不在该函数常量表里会追加进去
（luac50.dump 写回，已验证读写往返逐字节一致）。挪多少可以先用 sim_comic.check 试。
"""
import shutil, sys
import luac50
from project import game, original

SCRIPT = 'scripts/comics.lua'
ARGS = ('x', 'y', 'w', 'h')   # AddComicText_Aux 第 2~5 个参数（第 1 个是 t）

# {key: {参数: 新值}}
MOVES = {
    'comic_4_h': {'x': 243, 'y': 430},   # 原 241,422：两行字压在扁气泡上沿，右移 2、下移 8（模拟 r 1.17→0.95）
    'comic_5_f': {'x': 672},             # 原 667：文字比气泡中线偏左 5px，右移 5（模拟 r 1.07→0.96）
    # 以下按用户实机观感：文字偏左的右移到气泡中线（偏移量由 sim_comic 量出）
    'comic_3_f': {'x': 673},             # 原 668，偏左 5（r 1.12→0.94）
    'comic_5_g': {'x': 6},               # 原 0，偏左 6（r 0.98→0.83）
    'comic_7_b': {'x': 255},             # 原 250，偏左 5（r 0.99→0.91）
    'comic_7_c': {'x': 254},             # 原 250，偏左 4（r 1.01→0.90）
    'comic_7_n': {'x': 501},             # 原 486，偏左 15（r 1.09→0.76）
    'comic_2_f': {'y': 11},              # 原 7：首行偏在气泡变窄的上部，下移 4 落到气泡最宽处
}


def calls(f):
    """找出 AddComicText* 调用：[(函数, {参数名: LOADK 指令下标}, key)]"""
    out = []
    regs, base = {}, None
    for pc, i in enumerate(f['code']):
        op, A, Bx = i & 0x3f, i >> 24, (i >> 6) & 0x3ffff
        if op == 5 and isinstance(f['k'][Bx], str) and f['k'][Bx].startswith('AddComicText'):
            base, regs = A, {}
        elif op == 1 and base is not None:
            regs[A] = pc
        elif op == 29 and base is not None and A == base:   # CALL
            kpc = regs.get(base + 6)
            if kpc is not None:
                key = f['k'][(f['code'][kpc] >> 6) & 0x3ffff]
                out.append((f, {a: regs.get(base + 2 + n) for n, a in enumerate(ARGS)}, key))
            base = None
    for p in f['p']:
        out += calls(p)
    return out


def main():
    top = luac50.load(original(SCRIPT))
    found = {key: (f, pcs) for f, pcs, key in calls(top)}
    for key, change in MOVES.items():
        if key not in found:
            sys.exit(f'comics.lua 里没找到 {key}')
        f, pcs = found[key]
        for arg, v in change.items():
            pc = pcs[arg]
            if pc is None:
                sys.exit(f'{key} 的 {arg} 不是常量，无法直接改')
            i = f['code'][pc]
            old = f['k'][(i >> 6) & 0x3ffff]
            k = luac50.const_index(f, float(v))
            f['code'][pc] = (i & ~(0x3ffff << 6)) | (k << 6)
            print(f'  {key}.{arg}: {old:g} → {v}')
    open(game(SCRIPT), 'wb').write(luac50.dump(top))
    print('已写入', game(SCRIPT))


if __name__ == '__main__':
    if sys.argv[1:] == ['restore']:
        shutil.copy2(original(SCRIPT), game(SCRIPT)); print('已还原原版', SCRIPT)
    else:
        main()
