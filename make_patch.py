"""打包汉化补丁（给玩家下载的 zip）。游戏相关的设置见 project.json

  python make_patch.py 1.0      → dist/<patch_name>_v1.0.zip

内容：
  cn_patch/assets/...    改动过的游戏文件（project.json 的 patch_files，从当前游戏目录取，请先 apply / build 好）
  cn_patch/install.ps1   备份原版 → 复制补丁 → 按 patch_renames 把文件改名为 .bak（如 SOD 的漫画 swf）
                         → 按 patch_exe 原位修改 exe 里硬编码的英文（exe_patch.py 的 PATCHES；不附带整个 exe）
  cn_patch/uninstall.ps1 从备份还原（含 exe）
  安装汉化.bat / 卸载汉化.bat   只有一行，启动上面的 PowerShell 脚本
  使用说明.txt
  字体授权/              各字体的版权与授权协议

中文提示都放在 PowerShell 脚本里（UTF-8 带 BOM）：.bat 里写中文，存 UTF-8 会被 cmd 读错位，
存 GBK 又会在开了“UTF-8 全球语言支持”的系统上乱码；PowerShell 输出中文与代码页无关。
"""
import datetime, json, os, sys, zipfile
from project import ASSETS, CFG, HERE

FONTS_CFG = os.path.join(HERE, 'fonts.json')
FILES = CFG['patch_files']            # 相对 assets
RENAMES = CFG.get('patch_renames', [])  # 相对 assets 的通配符，如 "comic\\*.swf"
EXE = CFG['game_exe']
TITLE = f"《{CFG['title_cn']}》({CFG['title_en']})"

LAUNCH_BAT = '@echo off\r\npowershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0cn_patch\\{script}"\r\npause\r\n'

# 两个脚本共用的开头。@@名字@@ 由 ps1() 填入（PowerShell 本身大量用花括号，不用 str.format）
PS_HEAD = r'''$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Definition))
$Host.UI.RawUI.WindowTitle = '@@TITLE@@ 汉化补丁 @@ACTION@@'
$exe = '@@EXE@@'
$renames = @(@@RENAMES@@)

function Fail($msg) {
    Write-Host $msg -ForegroundColor Red
    exit 1
}

function CopyTo($src, $dst) {
    $dir = Split-Path -Parent $dst
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    Copy-Item -LiteralPath $src -Destination $dst -Force
}

$busy = '如果游戏正在运行，请先退出；如果游戏装在 Program Files 里，请右键“以管理员身份运行”。'
'''

INSTALL_PS1 = PS_HEAD + r'''$patchExe = $@@PATCH_EXE@@
# exe 补丁：(偏移, 原字节, 汉化后的字节)，由 make_patch.py 根据原版 exe 生成
$patches = @(
@@ROWS@@
)

if (-not (Test-Path -LiteralPath $exe)) {
    Fail "没有找到 $exe。`n请把压缩包里的全部内容解压到游戏目录（$exe 所在的文件夹）后再运行。"
}
if (-not (Test-Path -LiteralPath 'assets')) {
    Fail "没有找到 assets 文件夹。`n请把压缩包里的全部内容解压到游戏目录（$exe 所在的文件夹）后再运行。"
}
$files = @(Get-Content -LiteralPath 'cn_patch\filelist.txt' | Where-Object { $_ })

try {
    # 只在第一次安装时备份。原本不存在的文件（资源打包在 assets.pfp 里的版本，散文件会优先于 .pfp 读取）
    # 不会出现在备份里，卸载时据此判断是补丁新加的、要删掉
    if (-not (Test-Path -LiteralPath 'cn_backup')) {
        New-Item -ItemType Directory -Path 'cn_backup' | Out-Null
        Write-Host '正在备份原版文件到 cn_backup ...'
        foreach ($f in $files) {
            if (Test-Path -LiteralPath "assets\$f") { CopyTo "assets\$f" "cn_backup\assets\$f" }
        }
    }
    if ($patchExe -and -not (Test-Path -LiteralPath "cn_backup\$exe")) { CopyTo $exe "cn_backup\$exe" }
    Write-Host '正在安装汉化文件 ...'
    foreach ($f in $files) { CopyTo "cn_patch\assets\$f" "assets\$f" }
    foreach ($r in $renames) {
        Get-ChildItem -Path "assets\$r" | ForEach-Object { Rename-Item -LiteralPath $_.FullName -NewName ($_.Name + '.bak') }
    }
} catch {
    Fail ("安装失败：" + $_.Exception.Message + "`n" + $busy)
}

if ($patchExe) {
    # 先核对全部位置，任何一处和原版对不上就一个字节都不改；已改过的跳过
    Write-Host "正在修改 $exe 里的界面文字 ..."
    $msg = $null
    try {
        $path = (Resolve-Path -LiteralPath $exe).Path
        $data = [IO.File]::ReadAllBytes($path)
        $todo = @(); $done = 0
        foreach ($p in $patches) {
            $n = $p[1].Length / 2
            if ($p[0] + $n -gt $data.Length) { $msg = 'exe 版本和本补丁不符'; break }
            $cur = ([BitConverter]::ToString($data, $p[0], $n)) -replace '-', ''
            if ($cur -eq $p[2]) { $done++; continue }
            if ($cur -ne $p[1]) { $msg = ('exe 版本和本补丁不符（0x{0:x} 处和原版不一样）' -f $p[0]); break }
            $todo += ,$p
        }
        if (-not $msg) {
            foreach ($p in $todo) {
                for ($i = 0; $i -lt $p[2].Length; $i += 2) { $data[$p[0] + $i / 2] = [Convert]::ToByte($p[2].Substring($i, 2), 16) }
            }
            if ($todo.Count) { [IO.File]::WriteAllBytes($path, $data) }
            Write-Host ('已修改 {0} 处，{1} 处之前已改过。' -f $todo.Count, $done)
        }
    } catch {
        $msg = $_.Exception.Message
    }
    if ($msg) {
        Write-Host ''
        Write-Host "$exe 没有修改：$msg。" -ForegroundColor Yellow
        Write-Host '其余汉化文件已装好，只是“欢迎”“目标/专家”、连击等几处提示仍是英文。' -ForegroundColor Yellow
        Write-Host $busy -ForegroundColor Yellow
    }
}

Write-Host ''
Write-Host "安装完成！直接运行 $exe 即可。" -ForegroundColor Green
Write-Host '想恢复英文版，运行“卸载汉化.bat”。'
'''

UNINSTALL_PS1 = PS_HEAD + r'''if (-not (Test-Path -LiteralPath 'cn_backup')) {
    Fail '没有找到备份文件夹 cn_backup，无法还原。'
}
try {
    if (Test-Path -LiteralPath 'cn_backup\assets') {
        $base = (Resolve-Path -LiteralPath 'cn_backup\assets').Path
        Get-ChildItem -LiteralPath $base -Recurse | Where-Object { -not $_.PSIsContainer } | ForEach-Object {
            CopyTo $_.FullName ('assets\' + $_.FullName.Substring($base.Length + 1))
        }
    }
    # 补丁清单里有、备份里没有的文件，是安装时新加的（原版资源在 assets.pfp 里）：删掉，
    # 连同因此变空的、安装时新建的文件夹，游戏就会重新读 .pfp 里的原版
    $files = @(Get-Content -LiteralPath 'cn_patch\filelist.txt' | Where-Object { $_ })
    foreach ($f in $files) {
        if ((Test-Path -LiteralPath "cn_backup\assets\$f") -or -not (Test-Path -LiteralPath "assets\$f")) { continue }
        Remove-Item -LiteralPath "assets\$f" -Force
        $dir = Split-Path -Parent "assets\$f"
        while ($dir -and $dir -ne 'assets' -and (Test-Path -LiteralPath $dir) -and
               -not (Get-ChildItem -LiteralPath $dir -Force)) {
            Remove-Item -LiteralPath $dir -Force
            $dir = Split-Path -Parent $dir
        }
    }
    foreach ($r in $renames) {
        Get-ChildItem -Path "assets\$r.bak" | ForEach-Object { Rename-Item -LiteralPath $_.FullName -NewName ($_.Name -replace '\.bak$', '') }
    }
    if (Test-Path -LiteralPath "cn_backup\$exe") { Copy-Item -LiteralPath "cn_backup\$exe" -Destination $exe -Force }
} catch {
    Fail ("还原失败：" + $_.Exception.Message + "`n" + $busy)
}
Write-Host '已恢复为英文原版。' -ForegroundColor Green
'''

README_TXT = '''{title} 中文汉化补丁 v{ver}（{date}）

【安装】
1. 先退出游戏。把压缩包里的全部内容解压到游戏目录，也就是 {exe} 所在的文件夹。
2. 双击运行「安装汉化.bat」。原版文件（包括 {exe}）会自动备份到 cn_backup 文件夹。
   游戏装在 Program Files 里的话，请右键「以管理员身份运行」。

【卸载】
双击运行「卸载汉化.bat」，从 cn_backup 还原英文原版。

【说明】
- 资源为散文件的版本、以及资源打包在 assets\\assets.pfp 里的版本都适用
  （补丁文件放在 assets 文件夹里，游戏会优先读取它们；卸载时会删掉补丁新加的文件）。
- 本补丁为爱好者汉化，与 PlayFirst 及游戏开发商无关。请支持正版游戏。
- 译文与中文标志设计以 CC BY-NC 4.0 授权：可转载、修改，须署名，不得用于商业用途。
  字体授权见「字体授权」文件夹。

【制作】
翻译、润色、中文标志设计、图片修补、实机测试：艾登
试译、图片修补、字体排版与程序：Claude Opus 5.5
审校：Gemini 4 Argon
'''

HARMONY_NOTE = '''HarmonyOS Sans SC

版权归华为终端有限公司所有。依据其授权协议，字体可嵌入应用软件使用，
不得以独立形式重新分发或出售。本补丁的 .mvec 字体中如含有该字体的字形，
是将其转换为本游戏专用格式后嵌入游戏使用的，请勿将其提取作他用。
如需使用该字体，请从华为官方渠道获取：https://developer.huawei.com/consumer/cn/design/resource/
'''


def ps1(template, action, patch_exe):
    rows = ''
    if patch_exe:
        import exe_patch
        rows = ',\n'.join(f"    @(0x{off:x}, '{old.hex().upper()}', '{new.hex().upper()}')"
                          for off, old, new in exe_patch.regions())
    fill = {
        'TITLE': CFG['title_cn'], 'ACTION': action, 'EXE': EXE,
        'RENAMES': ', '.join("'" + p.replace("'", "''") + "'" for p in RENAMES),
        'PATCH_EXE': 'true' if patch_exe else 'false', 'ROWS': rows,
    }
    for k, v in fill.items():
        template = template.replace(f'@@{k}@@', v)
    return template.replace('\n', '\r\n').encode('utf-8-sig')   # Windows 自带的 PowerShell 5.1 要带 BOM 才按 UTF-8 读


def ofl_body():
    """从本地某个 OFL 字体包里取协议正文（去掉开头的版权行）；路径见 project.json 的 ofl_text"""
    ref = os.path.join(HERE, os.path.expandvars(CFG['ofl_text']))
    text = open(ref, encoding='utf-8', errors='replace').read()
    i = text.find('This Font Software is licensed under the SIL Open Font License')
    return text[i:] if i >= 0 else text


def font_copyright(path):
    from fontTools.ttLib import TTFont
    f = TTFont(os.path.expandvars(path), fontNumber=0, lazy=True)
    names = f['name']
    for lang in (0x804, 0x409, None):
        for r in names.names:
            if r.nameID == 0 and (lang is None or r.langID == lang):
                return r.toUnicode()
    return ''


def main():
    ver = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().strftime('%Y%m%d')
    os.makedirs(os.path.join(HERE, 'dist'), exist_ok=True)
    out = os.path.join(HERE, 'dist', f"{CFG['patch_name']}_v{ver}.zip")
    missing = [f for f in FILES if not os.path.exists(os.path.join(ASSETS, f))]
    if missing:
        sys.exit('游戏目录里缺少：' + ', '.join(missing))

    patch_exe = CFG.get('patch_exe', False)
    cfg = json.load(open(FONTS_CFG, encoding='utf-8'))
    base = os.path.dirname(FONTS_CFG)
    ofl = ofl_body()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in FILES:
            z.write(os.path.join(ASSETS, f), 'cn_patch/assets/' + f)
        z.writestr('cn_patch/filelist.txt', '\r\n'.join(f.replace('/', '\\') for f in FILES) + '\r\n')
        z.writestr('cn_patch/install.ps1', ps1(INSTALL_PS1, '安装', patch_exe))
        z.writestr('cn_patch/uninstall.ps1', ps1(UNINSTALL_PS1, '卸载', patch_exe))
        z.writestr('安装汉化.bat', LAUNCH_BAT.format(script='install.ps1'))
        z.writestr('卸载汉化.bat', LAUNCH_BAT.format(script='uninstall.ps1'))
        z.writestr('使用说明.txt', README_TXT.format(title=TITLE, exe=EXE, ver=ver, date=datetime.date.today())
                   .replace('\n', '\r\n'))
        sources = [f['source'] for f in cfg['fonts'].values()] + cfg.get('fallback', [])
        if any('HarmonyOS' in s for s in sources):
            z.writestr('字体授权/HarmonyOS Sans SC.txt', HARMONY_NOTE.replace('\n', '\r\n'))
        uses = {}       # 同一个字体可能装成几个游戏字体（如 rollout 和 comdigital），授权只写一份
        for name, f in cfg['fonts'].items():
            src = os.path.expandvars(f['source'])
            src = src if os.path.isabs(src) else os.path.join(base, src)
            if 'HarmonyOS' not in src:
                uses.setdefault(src, []).append(name)
        for src, names in uses.items():
            fam = os.path.splitext(os.path.basename(src))[0]
            z.writestr(f'字体授权/{fam}（{"、".join(names)}）.txt',
                       (f'{fam}\nCopyright: {font_copyright(src)}\n\n{ofl}').replace('\r\n', '\n').replace('\n', '\r\n'))
    size = os.path.getsize(out)
    print(f'已生成 {os.path.relpath(out, HERE)}（{size / 1048576:.1f} MB，{len(FILES)} 个游戏文件'
          + ('，含 exe 补丁' if patch_exe else '') + '）')


if __name__ == '__main__':
    main()
