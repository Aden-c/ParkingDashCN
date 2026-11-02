"""单字节文字：汉字 → 借用码位

exe 直接画的飘字、警告横幅（连击、洗车、额外小费、warning_text）按单字节处理，UTF-8 中文会乱码。
做法：在界面字体 rollout 里，把 ASCII 控制字符（1~31，跳过空白类和 0x1A）借来放中文字形，
文本里写这些控制字符。控制字符键盘打不出来，任何正常文本（包括玩家名）都不会出现，所以不会误伤。

  python bytepath.py        重新计算对照表 → bytepath_map.json，并写进 fonts.json 的 rollout.alias
                            （之后要 sh build_fonts.sh rollout、strings_tool apply、exe_patch）

zh.json 和 exe_patch.py 里都写正常中文，写入游戏时由 encode() 转换。
对照表会保留已分配的码位，新字才分配新码位，避免每次都变。
"""
import json, os, sys
from project import CFG, HERE, ZH

MAP = os.path.join(HERE, 'bytepath_map.json')
FONT = 'rollout'
# 跳过空白类控制字符 9~13（isspace 视为空白，可能被当成折行点）和 0x1A（Ctrl-Z，文本方式读文件时会被当成文件结尾）
POOL = ''.join(chr(c) for c in range(1, 32) if c not in (9, 10, 11, 12, 13, 26))
KEYS = CFG.get('byte_keys', [])   # strings.xml 里走单字节路径的条目


def load_map():
    return json.load(open(MAP, encoding='utf-8')) if os.path.exists(MAP) else {}


def encode(text, m=None):
    m = m if m is not None else load_map()
    out = []
    for ch in text:
        if ord(ch) < 0x80:
            out.append(ch)
        elif ch in m:
            out.append(m[ch])
        else:
            sys.exit(f'单字节文字里的“{ch}”还没分配码位，先运行 python bytepath.py')
    return ''.join(out)


def texts():
    """所有单字节路径的中文：strings.xml 的 byte_keys + exe_patch.py 里标了单字节的条目"""
    import exe_patch
    zh = json.load(open(ZH, encoding='utf-8'))
    return [zh[k] for k in KEYS if k in zh] + [new for _, _, new, byte in exe_patch.PATCHES if byte]


def main():
    m = {ch: code for ch, code in load_map().items() if code in POOL}
    need = sorted({ch for t in texts() for ch in t if ord(ch) >= 0x80}, key=ord)
    m = {ch: code for ch, code in m.items() if ch in need}   # 不再用到的字归还码位
    free = [c for c in POOL if c not in m.values()]
    for ch in need:
        if ch not in m:
            if not free:
                sys.exit(f'借用码位只有 {len(POOL)} 个，已用完，请精简单字节文字的用字')
            m[ch] = free.pop(0)
    json.dump(m, open(MAP, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    p = os.path.join(HERE, 'fonts.json')
    cfg = json.load(open(p, encoding='utf-8'))
    cfg['fonts'][FONT]['alias'] = {code: ch for ch, code in m.items()}
    json.dump(cfg, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'单字节用字 {len(need)} 个，剩余码位 {len(free)} 个：')
    print('  ' + ' '.join(f'{ch}={ord(code):02X}' for ch, code in m.items()))


if __name__ == '__main__':
    main()
