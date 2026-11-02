"""strings.xml 翻译工具（路径见 project.json）

  python strings_tool.py export        从 backup/ 里的英文原版 strings.xml 导出 en.json
  python strings_tool.py apply         把 zh.json 的译文写入游戏的 strings.xml（以英文原版为底）
  python strings_tool.py merge 批次.py  把 batches/xxx.py 的 T = {key: 译文} 并入 zh.json

JSON 里是纯文本：换行写 \n（对应 &#10;），<br> 等标签照写，脚本负责 XML 转义。
zh.json 里没有的 key 保持英文。
"""
import html, json, os, re, sys
from project import CFG, CHARSET as CS_PATH, EN, HERE, RAW_KEYS, ZH, game, original

SRC = original(CFG['strings'])
DST = game(CFG['strings'])

ROW = re.compile(r'<Row\b.*?</Row>', re.S)
DATA = re.compile(r'(<Data\b[^>]*>)(.*?)(</Data>)', re.S)


def unesc(s):
    return html.unescape(s)


def esc(s):
    s = s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    s = s.replace('\r\n', '\n').replace('\n', '&#10;')
    # 单字节文字借用的控制字符（见 bytepath.py）写成数字引用，文件里不出现原始控制字节
    return re.sub('[\x01-\x1f]', lambda m: f'&#{ord(m.group())};', s)


# ---- 中文折行点 ----
# 引擎对无空格的中文会多塞一个字才折行，但按空格折行是准的。
# 字体里空格做成了零宽（mkmvec --zero-space），这里在字间插入空格作为折行点，
# 原文中真正的空格换成 U+00A0（可见、不折行）。
NBSP = ' '
NO_BREAK_BEFORE = set('，。！？、；：）》」』〕】”’…—～·%,.!?;:)]}>')
NO_BREAK_AFTER = set('（《「『〔【“‘([{<')
TAG = re.compile(r'</?[A-Za-z]+>$')
CJK = re.compile(r'[⺀-鿿豈-﫿＀-￯　-〿‐-⁯]')


def _protected_words():
    """glossary.json 里的中文译名（人名、地名等）折行时不拆开"""
    path = os.path.join(HERE, 'glossary.json')
    if not os.path.exists(path):
        return []
    words = set()
    for _, zh, _ in json.load(open(path, encoding='utf-8')):
        words |= {w for w in re.split(r'[\s/／《》]+', zh) if len(w) > 1 and CJK.search(w)}
    return sorted(words, key=len, reverse=True)


# 标签、格式占位符（%1%、%%d、%d、$i）、译名整体作为一个记号，内部不插空格
TOKEN = re.compile('|'.join(map(re.escape, _protected_words())) + '|' +
                   r'''</?[A-Za-z]+>|%\d+%|%%?d|\n|[A-Za-z0-9_'\-+.,!?:;/&$#@*=()\[\]"]+|.''', re.S)


_jieba = None


def word_bounds(s):
    """jieba 分词得到的词语边界位置（中文只在词与词之间折行，“什么”“以为”不会被拆到两行）"""
    global _jieba
    if _jieba is None:
        try:
            import logging, jieba
            jieba.setLogLevel(logging.WARNING)
            for w in _protected_words():
                jieba.add_word(w)
            _jieba = jieba
        except ImportError:   # 没装 jieba 就退回逐字折行
            _jieba = False
    if not _jieba:
        return None
    return {end for _, _, end in _jieba.tokenize(s)}


def add_breaks(s):
    if not CJK.search(s):
        return s.replace(' ', NBSP)  # 纯英文：空格保持可见
    s = s.replace(' ', NBSP)
    bounds = word_bounds(s)
    spans = [(m.start(), m.group()) for m in TOKEN.finditer(s)]
    out = []
    hard = {'\n', '<br>', NBSP}
    for i, (pos, t) in enumerate(spans):
        if i:
            a, b = spans[i - 1][1], t
            if not (a in hard or b in hard
                    or b[0] in NO_BREAK_BEFORE or a[-1] in NO_BREAK_AFTER
                    or (TAG.match(a) and not a.startswith('</') and a != '<br>')  # 开标签之后
                    or (TAG.match(b) and b.startswith('</'))                       # 闭标签之前
                    or (bounds is not None and pos not in bounds
                        and CJK.match(a[-1]) and CJK.match(b[0]))):                # 词语内部
                out.append(' ')
        out.append(t)
    return ''.join(out)


def rows(text):
    for m in ROW.finditer(text):
        cells = list(DATA.finditer(m.group(0)))
        if len(cells) >= 2:
            yield m, cells


def export():
    text = open(SRC, encoding='utf-8', newline='').read()
    en = {unesc(c[0].group(2)): unesc(c[1].group(2)) for _, c in rows(text)}
    json.dump(en, open(EN, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'{len(en)} 条 -> {EN}')


def prebreak_targets():
    """可选的 boxes.py 提供需要预先断行的条目（漫画气泡等）"""
    try:
        import boxes
    except ImportError:
        return {}
    return boxes.prebreak_targets() if hasattr(boxes, 'prebreak_targets') else {}


def render(key, s, targets):
    """译文 → 写进 strings.xml 的文本（插折行点、按框宽预先断行）"""
    if key in RAW_KEYS:
        return s
    import bytepath
    if key in bytepath.KEYS:   # 单字节路径：汉字换成借用码位，不插折行点
        return bytepath.encode(s)
    if key in targets:
        s = s.replace('\r\n', '\n').replace('\n', '<br>')   # 译文里的手动换行（Excel 里 Alt+Enter）照排
    s = add_breaks(s)
    if key in targets and CJK.search(s):
        import prebreak
        s = prebreak.balance(s, *targets[key])
    return s


def apply():
    text = open(SRC, encoding='utf-8', newline='').read()
    zh = json.load(open(ZH, encoding='utf-8'))
    targets = prebreak_targets()
    out, last, n, nbsp, seen = [], 0, 0, 0, set()
    for m, cells in rows(text):
        key = unesc(cells[0].group(2))
        c = cells[1]
        if key in zh:
            seen.add(key)
            new = render(key, zh[key], targets); n += 1
        else:
            # 未翻译的英文：字体里空格是零宽的，要把空格换成 U+00A0 才看得见
            orig = unesc(c.group(2))
            if key in RAW_KEYS or ' ' not in orig:
                continue
            new = orig.replace(' ', NBSP); nbsp += 1
        a, b = m.start() + c.start(2), m.start() + c.end(2)
        out.append(text[last:a]); out.append(esc(new)); last = b
    out.append(text[last:])
    open(DST, 'w', encoding='utf-8', newline='').write(''.join(out))
    unknown = set(zh) - seen
    print(f'写入 {n} 条译文、{nbsp} 条未译英文（空格改为不换行空格）-> {DST}')
    if unknown:
        print('zh.json 中有未知 key:', ', '.join(sorted(unknown)))


PLACEHOLDER = re.compile(r'%\d+%|%%?d|\$[a-z]|</?[A-Za-z]+>')


def merge(path):
    """把 batches/xxx.py 里的 T = {key: 译文} 并入 zh.json，并做检查"""
    ns = {}
    exec(open(path, encoding='utf-8').read(), ns)
    en = json.load(open(EN, encoding='utf-8'))
    zh = json.load(open(ZH, encoding='utf-8'))
    cs_path = CS_PATH
    charset = set(open(cs_path, encoding='utf-8-sig').read()) | {'\n'}
    bad, newchars = False, set()
    auto = prebreak_targets()   # 这些条目由工具自动断行，原文的 <br> 不必保留
    for k, v in ns['T'].items():
        if k not in en:
            print('未知 key:', k); bad = True; continue
        a, b = sorted(PLACEHOLDER.findall(en[k])), sorted(PLACEHOLDER.findall(v))
        if k in auto:
            a, b = [t for t in a if t != '<br>'], [t for t in b if t != '<br>']
        if a != b and not re.search(r'[一-鿿]', en[k]):
            print(f'占位符不一致 {k}: 原文 {a} 译文 {b}')
        newchars |= set(v) - charset
    if bad:
        sys.exit('有错误，未合并')
    if newchars:  # 新字补进字符集，之后要重新生成字体
        open(cs_path, 'w', encoding='utf-8').write(''.join(sorted((charset | newchars) - {'\n'}, key=ord)))
        print('字符集新增:', ''.join(sorted(newchars)), '→ 需要运行 build_fonts.sh 重新生成字体')
    zh.update(ns['T'])
    json.dump(zh, open(ZH, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'合并 {len(ns["T"])} 条，zh.json 共 {len(zh)} / {len(en)} 条')


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'merge':
        merge(sys.argv[2])
    else:
        {'export': export, 'apply': apply}[cmd]()
