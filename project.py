"""读取 project.json，给各工具提供统一的路径（换游戏只改 project.json）"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, 'project.json'), encoding='utf-8'))


def _abs(p):
    p = os.path.expandvars(p)
    return os.path.normpath(p if os.path.isabs(p) else os.path.join(HERE, p))


ASSETS = _abs(CFG['game_assets'])
GAME_DIR = os.path.dirname(ASSETS)
BACKUP = _abs(CFG.get('backup', 'backup'))
EN = os.path.join(HERE, 'en.json')
ZH = os.path.join(HERE, 'zh.json')
CHARSET = os.path.join(HERE, 'charset.txt')
RAW_KEYS = set(CFG.get('raw_keys', []))
SKIP_KEYS = set(CFG.get('skip_keys', []))


def game(rel):
    """游戏 assets 里的文件"""
    return os.path.join(ASSETS, rel)


def original(rel):
    """backup/ 里的原版文件"""
    return os.path.join(BACKUP, rel)
