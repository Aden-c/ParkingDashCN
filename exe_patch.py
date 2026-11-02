"""把 exe 里硬编码的英文原位换成中文（UTF-8，长度不超过原串 + 其后的补零）

  python exe_patch.py           以 backup/ 里的原版 exe 为底打补丁，写入游戏目录
  python exe_patch.py restore   还原原版 exe

每一处都先核对原字节，对不上就停下，不会改坏别的版本的 exe。
"""
import os, shutil, sys
from project import CFG, GAME_DIR, BACKUP

EXE = os.path.join(GAME_DIR, CFG['game_exe'])
ORIG = os.path.join(BACKUP, CFG['game_exe'])

# (文件偏移, 原文, 译文, 单字节)。可用长度 = 原文长度 + 其后连续的 \0 - 1（留一个结束符）
# 单字节=True：这段文字走单字节渲染路径，写入前由 bytepath.encode() 把汉字换成借用码位
PATCHES = [
    (0x16caf0, b'Welcome, ', '欢迎，', False),                     # 主菜单底栏“Welcome, 玩家名”
    (0x16e0f0, b'<outline color="666666" size="0">EXPERT:\n', '<outline color="666666" size="0">专家：\n', False),  # HUD
    (0x16e20c, b'<outline color="666666" size="0">GOAL: \n', '<outline color="666666" size="0">目标：\n', False),   # HUD
    (0x16be70, b'%d, ', '%d，', False),                            # 结算“最佳连击 x3, 得分”
    (0x16fe78, b'Best Score: ', '最高分：', False),                  # 选关地图上每关的最高分
    # 飘字：单字节路径
    (0x16ed18, b'car wash x%d!', '洗车x%d!', True),
    (0x16ed2c, b'combo x%d!', '连击x%d!', True),
    (0x16ed40, b'combo x%d max!', '最高连击x%d', True),
]


def room(data, off, orig):
    end = off + len(orig)
    while end < len(data) and data[end] == 0:
        end += 1
    return end - off - 1


def regions(verbose=False):
    """按原版 exe 算出每处要写的字节：[(偏移, 原字节, 新字节)]，两者等长（含其后的补零）。
    make_patch.py 用它生成玩家电脑上运行的补丁脚本"""
    data = open(ORIG, 'rb').read()
    import bytepath
    m = bytepath.load_map()
    out = []
    for off, orig, new, byte in PATCHES:
        if byte:
            new = bytepath.encode(new, m)
        if data[off:off + len(orig)] != orig or data[off + len(orig)] != 0:
            sys.exit(f'0x{off:x} 处不是 {orig!r}，exe 版本不同，未修改')
        nb = new.encode('utf-8')
        n = room(data, off, orig)
        if len(nb) > n:
            sys.exit(f'0x{off:x} 译文 {new!r} 有 {len(nb)} 字节，超过可用的 {n} 字节')
        out.append((off, data[off:off + n + 1], nb + b'\0' * (n + 1 - len(nb))))
        if verbose:
            print(f'  0x{off:x}  {orig.decode()!r:<46} → {new!r}（{len(nb)}/{n} 字节）')
    return out


def main():
    if not os.path.exists(ORIG):
        os.makedirs(BACKUP, exist_ok=True)
        shutil.copy2(EXE, ORIG)
        print('已备份原版 exe →', ORIG)
    data = bytearray(open(ORIG, 'rb').read())
    for off, _, new in regions(verbose=True):
        data[off:off + len(new)] = new
    open(EXE, 'wb').write(data)
    print('已写入', EXE)


if __name__ == '__main__':
    if sys.argv[1:] == ['restore']:
        shutil.copy2(ORIG, EXE); print('已还原原版 exe')
    else:
        main()
