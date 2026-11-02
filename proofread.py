"""校对表导出 / 导入

  python proofread.py export   生成 校对表.xlsx（覆盖前会备份旧表）
  python proofread.py import   读取 校对表.xlsx 中“修改后译文”非空的行 → batches/b_proofread_日期.py → 并入 zh.json
"""
import datetime, json, os, re, shutil, sys
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

from project import CFG, EN as EN_PATH, HERE, SKIP_KEYS as SKIP, ZH as ZH_PATH

XLSX = os.path.join(HERE, '校对表.xlsx')
EN = json.load(open(EN_PATH, encoding='utf-8'))
ZH = json.load(open(ZH_PATH, encoding='utf-8'))

# 分类（按游戏中出现的大致顺序）：project.json 的 proofread_categories = [[名称, [key 前缀...]], ...]，第一类是兜底
CATS = [(name, tuple(p) if p else None) for name, p in CFG.get('proofread_categories', [['界面', None]])]
# 译名表：glossary.json = [[英文, 译名, 说明], ...]
GLOSSARY_PATH = os.path.join(HERE, 'glossary.json')
GLOSSARY = json.load(open(GLOSSARY_PATH, encoding='utf-8')) if os.path.exists(GLOSSARY_PATH) else []


def category(key):
    for name, prefixes in CATS[1:]:
        if key.startswith(prefixes):
            return name
    return '界面'


def box_sizes():
    """每个 key 的显示空间说明（文字框宽度、气泡尺寸等）。各游戏不同，由可选的 boxes.py 提供"""
    try:
        import boxes
    except ImportError:
        return {}
    return boxes.box_sizes()


def export():
    keep = {}   # 沿用旧表的“状态”“备注”，校对进度不丢
    if os.path.exists(XLSX):
        ws0 = load_workbook(XLSX)['校对']
        h0 = [c.value for c in ws0[1]]
        for row in ws0.iter_rows(min_row=2, values_only=True):
            keep[row[h0.index('Key')]] = (row[h0.index('状态')], row[h0.index('备注')])
        bak = XLSX.replace('.xlsx', datetime.datetime.now().strftime('_%Y%m%d_%H%M%S.xlsx'))
        shutil.copy(XLSX, bak)
        print('旧表已备份为', os.path.basename(bak))
    sizes = box_sizes()
    order = {name: i for i, (name, _) in enumerate(CATS)}
    keys = [k for k in EN if k not in SKIP and k in ZH]
    keys.sort(key=lambda k: order[category(k)])  # 稳定排序：同类内保持原文件顺序

    F = '微软雅黑'
    font, bold = Font(name=F, size=10), Font(name=F, size=10, bold=True, color='FFFFFF')
    head_fill = PatternFill('solid', fgColor='5B4A8B')
    input_fill = PatternFill('solid', fgColor='FFF2CC')
    thin = Side(style='thin', color='D9D9D9'); border = Border(bottom=thin)
    wrap = Alignment(wrap_text=True, vertical='top')

    wb = Workbook()
    ws = wb.active; ws.title = '校对'
    heads = ['序号', '分类', 'Key', '原文', '当前译文', '修改后译文', '状态', '备注', '显示空间']
    widths = [6, 10, 26, 48, 42, 42, 8, 24, 18]
    for c, (h, w) in enumerate(zip(heads, widths), 1):
        cell = ws.cell(1, c, h); cell.font = bold; cell.fill = head_fill
        cell.alignment = Alignment(vertical='center', horizontal='center')
        ws.column_dimensions[cell.column_letter].width = w
    for r, k in enumerate(keys, 2):
        en = EN[k] if not re.search(r'[一-鿿]', EN[k]) else '（英文原文已丢失）'
        st, note = keep.get(k, (None, None))
        row = [r - 1, category(k), k, en, ZH[k], None, st, note, sizes.get(k, '')]
        for c, v in enumerate(row, 1):
            cell = ws.cell(r, c, v); cell.font = font; cell.alignment = wrap; cell.border = border
            if c in (6, 7, 8):
                cell.fill = input_fill
    ws.freeze_panes = 'F2'
    ws.auto_filter.ref = f'A1:I{len(keys) + 1}'
    dv = DataValidation(type='list', formula1='"已校,有疑问,需改"', allow_blank=True)
    ws.add_data_validation(dv); dv.add(f'G2:G{len(keys) + 1}')

    # 译名表
    g = wb.create_sheet('译名表')
    for c, (h, w) in enumerate(zip(['英文', '译名', '说明'], [28, 20, 36]), 1):
        cell = g.cell(1, c, h); cell.font = bold; cell.fill = head_fill
        g.column_dimensions[cell.column_letter].width = w
    for r, row in enumerate(GLOSSARY, 2):
        for c, v in enumerate(row, 1):
            g.cell(r, c, v).font = font
    g.freeze_panes = 'A2'

    # 说明
    s = wb.create_sheet('说明', 0)
    s.column_dimensions['A'].width = 16; s.column_dimensions['B'].width = 80
    n = len(keys) + 1
    rows = [
        (f"{CFG['title_cn']} 汉化校对表", None),
        (None, None),
        ('怎么填', '只在「校对」页的黄色三列里填写：'),
        ('修改后译文', '想改哪条，就把新译文写在这一列；不改的留空。换行直接在单元格里按 Alt+Enter。'),
        ('状态', '下拉选择：已校 / 有疑问 / 需改（可选，方便自己筛选进度）'),
        ('备注', '写给我的说明，例如“这句在游戏里溢出了”“语气太生硬”'),
        (None, None),
        ('注意', '<br>、<b>、%1%、%%d 等是游戏里的换行/格式/数字占位符，修改时要原样保留。'),
        ('', '「显示空间」列是文字框宽度（像素），漫画气泡约每行可放的字数仅供参考。'),
        ('', '中文字之间不用加空格，换行由工具自动处理。'),
        (None, None),
        ('进度', None),
        ('总条数', f'=COUNTA(校对!C2:C{n})'),
        ('已填修改', f'=COUNTA(校对!F2:F{n})'),
        ('标为已校', f'=COUNTIF(校对!G2:G{n},"已校")'),
        ('有疑问/需改', f'=COUNTIF(校对!G2:G{n},"有疑问")+COUNTIF(校对!G2:G{n},"需改")'),
    ]
    for r, (a, b) in enumerate(rows, 1):
        ca, cb = s.cell(r, 1, a), s.cell(r, 2, b)
        ca.font = Font(name=F, size=10, bold=True); cb.font = font
        cb.alignment = Alignment(wrap_text=True, vertical='top', horizontal='left')
    s['A1'].font = Font(name=F, size=14, bold=True, color='5B4A8B')
    wb.calculation.fullCalcOnLoad = True  # 说明页的统计公式在 Excel 打开时计算
    wb.save(XLSX)
    print(f'已生成 {os.path.basename(XLSX)}：{len(keys)} 条')


def do_import():
    wb = load_workbook(XLSX)
    ws = wb['校对']
    head = [c.value for c in ws[1]]
    ik, inew = head.index('Key'), head.index('修改后译文')
    T = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[inew] not in (None, ''):
            T[row[ik]] = str(row[inew]).replace('\r\n', '\n').strip()
    if not T:
        print('没有填写修改后译文的行'); return
    path = os.path.join(HERE, 'batches', datetime.datetime.now().strftime('b_proofread_%Y%m%d_%H%M.py'))
    open(path, 'w', encoding='utf-8').write('# 校对表导入\nT = ' + json.dumps(T, ensure_ascii=False, indent=1) + '\n')
    print(f'读取到 {len(T)} 条修改 → {os.path.relpath(path, HERE)}')
    sys.path.insert(0, HERE)
    import strings_tool
    strings_tool.merge(path)


if __name__ == '__main__':
    {'export': export, 'import': do_import}[sys.argv[1]]()
