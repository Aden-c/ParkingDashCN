"""制作人员名单：以 backup/ 里的原版名单为底，翻译职位与说明句，人名保留英文
   python credits_tool.py   → 写入游戏（路径见 project.json 的 credits）

   原版是 Latin-1 编码，写回时一律存成 UTF-8（不带 BOM），和 strings.xml 一致。"""
import re
from project import CFG, game, original
from strings_tool import add_breaks

SRC = original(CFG['credits'])
DST = game(CFG['credits'])

ROLES = {   # 原版名单里的职位标题
    'CEO & Executive Producer': '首席执行官兼执行制作人', 'Producers': '制作人',
    'Software Engineering': '软件工程', 'Artists': '美术', 'Quality Assurance': '质量保证',
    'Senior Producer': '高级制作人', 'Associate Producer': '助理制作人', 'Game Designer': '游戏设计',
    'Art Consultant': '美术顾问', 'QA Manager': '质量保证经理', 'Art Director': '美术总监',
    'Director of Publishing': '发行总监', 'VP, Creative Director': '副总裁、创意总监',
    'Director of Engineering': '技术总监', 'Playground Game Engine': 'Playground 游戏引擎',
    'Audio': '音频', 'Special Thanks': '特别感谢',
}
TITLES = {  # 人名后括号里的头衔
    'Lead Engineer': '首席工程师', 'Lead Artist': '首席美术', 'QA Lead': '质量保证负责人',
    'Project Lead': '项目负责人', 'Lead': '负责人',
}
LINES = {
    'Copyright © 2008 PlayFirst, Inc.  All rights reserved.': 'Copyright © 2008 PlayFirst, Inc. 保留一切权利。',
    'PlayFirst, Parking Dash, DinerTown, and all related titles, logos, and characters are trademarks of PlayFirst, Inc.':
        'PlayFirst、Parking Dash、DinerTown 及所有相关名称、标志和角色均为 PlayFirst, Inc. 的商标。',
    'Parking Dash and PlayFirst are registered in the U.S. and other countries.':
        'Parking Dash 和 PlayFirst 已在美国及其他国家注册。',
    'Kef Sensei is a trademark of Kef Sensei, LLC.': 'Kef Sensei 是 Kef Sensei, LLC. 的商标。',
    'Protected by copyright and licenses restricting use, copying, distribution and decompilation.':
        '受版权及许可协议保护，限制使用、复制、分发和反编译。',
}


# 汉化人员，放在名单最前面（两栏各宽 300px、16 号字，职位标题每行别超过 ~18 个字）
HANHUA = [
    '[[中文汉化]]',
    '',
    '[翻译、润色]',
    '艾登',
    '',
    '[试译]',
    'Claude Opus 5.5',
    '',
    '[审校]',
    'Gemini 4 Argon',
    '',
    '[中文标志设计]',
    '艾登',
    '',
    '[图片修补]',
    '艾登',
    'Claude Opus 5.5',
    '',
    '[字体、排版与程序]',
    'Claude Opus 5.5',
    '',
    '[实机测试]',
    '艾登',
    '',
    '',
]


def convert(line):
    s = line.strip()
    m = re.fullmatch(r'\[(.*)\]', s)
    if m and m.group(1) in ROLES:
        s = '[' + ROLES[m.group(1)] + ']'
    elif s in LINES:
        s = LINES[s]
    else:
        m = re.fullmatch(r'(.*?)\s*\((.*)\)', s)    # 人名 (头衔) → 人名（头衔）
        if m and m.group(2) in TITLES:
            return convert(m.group(1)) + add_breaks('（' + TITLES[m.group(2)] + '）')
    if re.search(r'[一-鿿]', s):
        return add_breaks(s)
    # 纯英文（人名等）：空格可见且不折行，只在逗号后允许折行
    return s.replace(' ', ' ').replace(', ', ',  ')


def main():
    raw = open(SRC, 'rb').read()
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:  # Parking Dash 的原版名单是 Latin-1（© = 0xA9）；引擎能否读 UTF-8 中文待实测
        text = raw.decode('latin-1')
    lines = text.split('\r\n')
    # 去掉开头的破解组留言（[[Cracked By]] 到其后第一个空行），它不属于原版名单
    if '[[Cracked By]]' in lines[0]:
        lines = lines[lines.index('') + 1:]
    out = '\r\n'.join(convert(l) for l in HANHUA + lines)
    open(DST, 'w', encoding='utf-8', newline='').write(out)
    print('credits.txt 已写入')


if __name__ == '__main__':
    main()
