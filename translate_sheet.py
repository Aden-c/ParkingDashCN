"""翻译表：把还没翻译的条目导出成 Excel，填好后导入

  python translate_sheet.py export   生成 翻译表.xlsx（已存在时先备份，并沿用旧表里填过的译文和备注；
                                     旧表里的行全部保留，另外加入排版检查标出的问题条目，并刷新漫画模拟图）
  python translate_sheet.py import   读取“译文”列 → batches/b_translate_日期.py → 并入 zh.json
                                     只采用导出后改过的格子（对照 翻译表_快照.json），没动过的格子
                                     不会覆盖 zh.json 里在别处做的修改；原文相同、译文留空的行自动沿用
  python translate_sheet.py set KEY 译文   改 zh.json 里的一条，同时写进翻译表和快照（表没在 Excel 里打开时）
"""
import datetime, json, os, re, shutil, sys
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from project import CFG, EN as EN_PATH, HERE, RAW_KEYS, SKIP_KEYS, ZH as ZH_PATH
from proofread import CATS, GLOSSARY, box_sizes, category

XLSX = os.path.join(HERE, '翻译表.xlsx')
SNAP = os.path.join(HERE, '翻译表_快照.json')   # 导出（或同步）时表里的译文；导入时只采用和它不同的格子
EN = json.load(open(EN_PATH, encoding='utf-8'))
ZH = json.load(open(ZH_PATH, encoding='utf-8'))

# 漫画 key → 图片与剧情位置（comics.lua：comic_1~3 是开头三页，之后每个世界开场一页）
COMIC_PAGES = {1: ('comics_1_1', '开场第 1 页'), 2: ('comics_1_2', '开场第 2 页'), 3: ('comics_1_3', '开场第 3 页'),
               4: ('comics_2_1', '进入婚礼城堡前'), 5: ('comics_3_1', '进入唐人街前'), 6: ('comics_4_1', '进入海滩前'),
               7: ('comics_5_1', '进入月球前'), 8: ('comics_6_1', '结局')}
WORLDS = ['弗洛餐厅', '婚礼城堡', '唐人街', '海滩', '月球']
UPGRADE_NAMES = ('Fast car wash', 'Fast walk', 'Parking size', 'Faster donnuts', 'Faster snow clean', 'Faster sand sweeping',
                 'Faster flowers sweeping', 'Cookies for dog', 'Car Wash Assistant', 'Drink for customers', 'Parking system')
TAGS = re.compile(r'</?[A-Za-z]+>|%\d+%|%%?d')


def todo_keys(extra=()):
    """待译条目 + extra（旧表里已有的行、排版有问题的条目）"""
    keys = [k for k in EN if (k not in ZH or k in extra) and k not in SKIP_KEYS and k not in RAW_KEYS and EN[k].strip()]
    order = {name: i for i, (name, _) in enumerate(CATS)}
    return sorted(keys, key=lambda k: order[category(k)])  # 稳定排序：同类内保持原文件顺序


def hint(k):
    en, notes = EN[k], []
    m = re.match(r'comic_(\d+)_', k)
    if m:
        img, where = COMIC_PAGES[int(m.group(1))]
        notes.append(f'漫画·{where}（图片 comics/{img}.jpg）')
        if '<br>' in en:
            notes.append('原文的 <br> 是英文的手动换行，不用照搬；想自己分行就按 Alt+Enter')
    m = re.match(r'intro_level_(\d+)$', k)
    if m:
        n = int(m.group(1))
        notes.append(f'第 {n} 关开场，世界：{WORLDS[(n - 1) // 10]}')
    if k == 'intro_level_endless':
        notes.append('无尽轮班模式开场')
    if k.startswith(UPGRADE_NAMES):
        notes.append('升级项名称')
    if k.startswith('radio_genre_'):
        notes.append('电台曲风名（选电台窗口）')
    tags = [t for t in TAGS.findall(en) if not (k.startswith('comic_') and t == '<br>')]
    if tags:
        notes.append('请保留：' + ' '.join(dict.fromkeys(tags)))
    if '%1%' in en:
        notes.append('%1% 是程序填入的数字/名字')
    if '%%d' in en:
        notes.append('%%d 是数字')
    if en != en.strip() or en.startswith('  '):
        notes.append('原文首尾有空格（排版用），译文可不管')
    return '；'.join(notes)


def style():
    F = '微软雅黑'
    return dict(
        F=F, font=Font(name=F, size=10), bold=Font(name=F, size=10, bold=True, color='FFFFFF'),
        head=PatternFill('solid', fgColor='5B4A8B'), inp=PatternFill('solid', fgColor='FFF2CC'),
        border=Border(bottom=Side(style='thin', color='D9D9D9')), wrap=Alignment(wrap_text=True, vertical='top'))


def header(ws, heads, widths, S):
    for c, (h, w) in enumerate(zip(heads, widths), 1):
        cell = ws.cell(1, c, h); cell.font = S['bold']; cell.fill = S['head']
        cell.alignment = Alignment(vertical='center', horizontal='center')
        ws.column_dimensions[cell.column_letter].width = w


def export():
    keep = {}   # 沿用旧表已填的译文和备注
    if os.path.exists(XLSX):
        ws0 = load_workbook(XLSX)['翻译']
        h0 = [c.value for c in ws0[1]]
        for row in ws0.iter_rows(min_row=2, values_only=True):
            keep[row[h0.index('Key')]] = (row[h0.index('译文')], row[h0.index('备注')])
        bak = XLSX.replace('.xlsx', datetime.datetime.now().strftime('_%Y%m%d_%H%M%S.xlsx'))
        shutil.copy(XLSX, bak)
        print('旧表已备份为', os.path.basename(bak))

    import boxes, subprocess
    issues = boxes.layout_issues(ZH)
    for n in boxes.COMIC_PAGES:   # 8 页漫画模拟图都刷新
        subprocess.run([sys.executable, '-X', 'utf8', os.path.join(HERE, 'sim_comic.py'), str(n), '--outline'],
                       check=True, capture_output=True)
    S, sizes, keys = style(), box_sizes(), todo_keys(set(keep) | set(issues))
    mark = {'放不下': PatternFill('solid', fgColor='F4B6B6'), '出界': PatternFill('solid', fgColor='F8CBAD'),
            '贴边': PatternFill('solid', fgColor='FFE699')}
    wb = Workbook()
    ws = wb.active; ws.title = '翻译'
    header(ws, ['序号', '分类', 'Key', '原文', '译文', '备注', '显示空间', '提示'], [6, 10, 22, 52, 46, 20, 22, 30], S)
    first = {}
    for r, k in enumerate(keys, 2):
        h = hint(k)
        if EN[k] in first:
            h = (f'与第 {first[EN[k]]} 行原文相同，可留空自动沿用；' + h).rstrip('；')
        else:
            first[EN[k]] = r - 1
        tr, note = keep.get(k, (None, None))
        if tr in (None, '') and k in ZH:
            tr = ZH[k]
        if k in issues:
            h = (f'【排版·{issues[k][0]}】{issues[k][1]}；' + h).rstrip('；')
        row = [r - 1, category(k), k, EN[k], tr, note, sizes.get(k, ''), h]
        for c, v in enumerate(row, 1):
            cell = ws.cell(r, c, v); cell.font = S['font']; cell.alignment = S['wrap']; cell.border = S['border']
            if c in (5, 6):
                cell.fill = S['inp']
            if c == 8 and k in issues:
                cell.fill = mark[issues[k][0]]
    ws.freeze_panes = 'E2'
    ws.auto_filter.ref = f'A1:H{len(keys) + 1}'

    # 已译条目，供统一用词参考
    ref = wb.create_sheet('已译参考')
    header(ref, ['分类', 'Key', '原文', '译文'], [10, 22, 52, 46], S)
    for r, k in enumerate([k for k in EN if k in ZH], 2):
        for c, v in enumerate([category(k), k, EN[k], ZH[k]], 1):
            cell = ref.cell(r, c, v); cell.font = S['font']; cell.alignment = S['wrap']
    ref.freeze_panes = 'C2'

    g = wb.create_sheet('译名表')
    header(g, ['英文', '译名', '说明'], [28, 20, 36], S)
    for r, row in enumerate(GLOSSARY, 2):
        for c, v in enumerate(row, 1):
            g.cell(r, c, v).font = S['font']
    g.freeze_panes = 'A2'

    s = wb.create_sheet('说明', 0)
    s.column_dimensions['A'].width = 16; s.column_dimensions['B'].width = 84
    n = len(keys) + 1
    rows = [
        (f"{CFG['title_cn']} 翻译表", None),
        (None, None),
        ('怎么填', '在「翻译」页的黄色两列填写：「译文」写中文；「备注」写给我的话（拿不准、需要我查的地方等）。'),
        ('', '只填一部分也可以导入，没填的保持英文，之后可以重新导出接着填（已填的会保留）。'),
        ('原文相同', '「提示」列标了“与第 N 行原文相同”的，译文可以留空，导入时自动沿用。'),
        (None, None),
        ('不用操心的', '中文字之间不用加空格，折行、避头尾、漫画和教程的分行都由工具自动处理。'),
        ('', '漫画原文里的 <br> 是英文的手动换行，中文不用照搬。'),
        ('漫画换行', '漫画台词可以自己换行：在单元格里按 Alt+Enter，工具就照你的分行排（某行超出气泡框宽时才会再折）。'),
        ('', '排成中间宽、上下窄的形状最能塞进椭圆气泡，往往不用删字。'),
        ('排版检查', '「提示」列标了【排版·放不下/出界/贴边】并着色的，是按游戏规则模拟后发现文字会超出或贴着气泡边缘的台词，'),
        ('', '译文已预填现在的版本，直接在上面改。模拟图在 hanhua/preview/comic_N.png：红框=出界，橙框=贴边，蓝框=正常。'),
        ('要保留的', '<b>…</b>（粗体）、<br>（换行，帮助页顾客介绍那种列表结构要保留）、%1%、%%d（程序填入的数字）。'),
        ('', '不要用 { } [ ] ^ ` | ~ # @ 这几个符号：它们在字体里被借去显示飘字的中文了。'),
        ('显示空间', '文字框的像素尺寸和大约每行能放的字数，超出太多会被挤出框外，仅供参考；拿不准就照写，进游戏看了再改。'),
        ('参考', '「已译参考」页是已经翻好的 140 条，「译名表」页是人名地名等统一译法。'),
        (None, None),
        ('进度', None),
        ('总条数', f'=COUNTA(翻译!C2:C{n})'),
        ('已填译文', f'=COUNTA(翻译!E2:E{n})'),
    ]
    for r, (a, b) in enumerate(rows, 1):
        ca, cb = s.cell(r, 1, a), s.cell(r, 2, b)
        ca.font = Font(name=S['F'], size=10, bold=True); cb.font = S['font']
        cb.alignment = Alignment(wrap_text=True, vertical='top', horizontal='left')
    s['A1'].font = Font(name=S['F'], size=14, bold=True, color='5B4A8B')
    wb.calculation.fullCalcOnLoad = True
    wb.save(XLSX)
    save_snapshot()
    print(f'已生成 {os.path.basename(XLSX)}：{len(keys)} 条（其中排版需调整 {len(issues)} 条，已沿用旧表译文 {sum(1 for v in keep.values() if v[0])} 条）')


def _cell(v):
    return '' if v in (None, '') else str(v).replace('\r\n', '\n').strip()


def sheet_rows():
    ws = load_workbook(XLSX)['翻译']
    head = [c.value for c in ws[1]]
    ik, ien, itr = head.index('Key'), head.index('原文'), head.index('译文')
    return [(r[ik], r[ien], _cell(r[itr])) for r in ws.iter_rows(min_row=2, values_only=True) if r[ik]]


def save_snapshot():
    json.dump({k: tr for k, _, tr in sheet_rows()}, open(SNAP, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


def do_import():
    rows = sheet_rows()
    snap = json.load(open(SNAP, encoding='utf-8')) if os.path.exists(SNAP) else {}
    T, by_en, same = {}, {}, 0
    for k, en, tr in rows:
        if tr:
            by_en.setdefault(en, tr)
            if k in snap and snap[k] == tr and k in ZH:
                same += 1        # 导出后没改过：不覆盖 zh.json（那里可能有在别处做的修改）
                continue
            T[k] = tr
    auto = {k: by_en[en] for k, en, tr in rows if not tr and k not in ZH and en in by_en}
    T.update(auto)
    if not T:
        print(f'没有改过的格子（{same} 格与导出时相同）'); return
    path = os.path.join(HERE, 'batches', datetime.datetime.now().strftime('b_translate_%Y%m%d_%H%M.py'))
    open(path, 'w', encoding='utf-8').write('# 翻译表导入\nT = ' + json.dumps(T, ensure_ascii=False, indent=1) + '\n')
    print(f'读取到 {len(T) - len(auto)} 条改过的译文（{same} 格未改动、已跳过），另有 {len(auto)} 条按相同原文自动沿用 → {os.path.relpath(path, HERE)}')
    import strings_tool
    strings_tool.merge(path)
    save_snapshot()


def do_set(key, text):
    """改 zh.json 的一条，并同步到翻译表（若有这一行）和快照"""
    import strings_tool
    text = text.replace('\\n', '\n')   # 命令行里写 \n 表示换行
    path = os.path.join(HERE, 'batches', datetime.datetime.now().strftime('b_set_%Y%m%d_%H%M%S.py'))
    open(path, 'w', encoding='utf-8').write('# translate_sheet.py set\nT = ' + json.dumps({key: text}, ensure_ascii=False) + '\n')
    strings_tool.merge(path)
    wb = load_workbook(XLSX); ws = wb['翻译']
    head = [c.value for c in ws[1]]
    ik, itr = head.index('Key') + 1, head.index('译文') + 1
    for r in range(2, ws.max_row + 1):
        if ws.cell(r, ik).value == key:
            ws.cell(r, itr).value = text
            wb.save(XLSX); print('翻译表已同步')
            break
    save_snapshot()


if __name__ == '__main__':
    if sys.argv[1] == 'set':
        do_set(sys.argv[2], sys.argv[3])
    else:
        {'export': export, 'import': do_import}[sys.argv[1]]()
