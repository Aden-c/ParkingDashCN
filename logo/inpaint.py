"""擦掉主菜单背景 welcomem.jpg 上的英文 logo

  python logo/inpaint.py      读 backup/backgrounds/welcomem.jpg → logo/mask.png、logo/welcomem_clean.png

步骤：
  1. 蒙版：logo 的白描边围住的区域 + 四周一圈；阴影偏左上，所以左上多扩一些
  2. LaMa 修补（onnxruntime 本机运行，输入固定 512×512）：先整图缩小补一遍定大结构，
     再裁 logo 附近放大、只补内圈细化
  3. 压平：AI 补出的纹理偏斑驳，用周围画面的颜色聚类成平涂色块，接近原画的卡通风格
  4. 天际线：按补出的天空/楼群分界取台阶形轮廓，天空按行取原图颜色，楼群平涂紫色，加深色勾线
  5. 下半截按原画结构铺：楼群到地面线，下面马路；树冠被盖住的右半边用露出的左半边镜像补上
  6. 中文 logo 露出的部分手工修：左上重排三栋楼，米色车顶按用户画的车顶线分色
蒙版外的像素保持原样（边缘羽化 1~2 像素）。
模型：huggingface.co/Carve/LaMa-ONNX 的 lama_fp32.onnx，放在本目录。
"""
import os

import cv2
import numpy as np
import onnxruntime as ort
from scipy.ndimage import median_filter

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'backup', 'backgrounds', 'welcomem.jpg')
MASK = os.path.join(HERE, 'mask.png')
MODEL = os.path.join(HERE, 'lama_fp32.onnx')
OUT = os.path.join(HERE, 'welcomem_clean.png')

ROI = (slice(5, 235), slice(10, 345))   # logo 所在范围（行, 列）
TM = (slice(172, 190), slice(290, 312))  # ™ 符号
SKY = np.array([254, 255, 146.])        # BGR：天空青色
LAV = np.array([218, 172, 185.])        # 远处楼群的淡紫色
INK = np.array([57, 24, 21])            # 勾线深蓝
SKYLINE_ROWS = 130                      # 只在这条线以上重画天际线


def _ellipse(n):
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (n, n))


def make_mask(img):
    """logo 的白描边（纯白、大块连通）→ 上下左右都被描边包住的点算 logo 内部 → 外扩"""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    white = np.zeros(hsv.shape[:2], bool)
    white[ROI] = ((hsv[..., 1] < 30) & (hsv[..., 2] > 242))[ROI]
    n, lab, st, _ = cv2.connectedComponentsWithStats(white.astype(np.uint8), 8)
    ring = np.isin(lab, [i for i in range(1, n) if st[i, 4] > 300])

    def between(a, axis):
        c = np.cumsum(a, axis=axis)
        return ((c > 0) & (c < np.take(c, [-1], axis=axis))) | a
    core = (between(ring, 1) & between(ring, 0)).astype(np.uint8)
    core[TM] = 1
    core = cv2.morphologyEx(core, cv2.MORPH_CLOSE, _ellipse(9))
    near = cv2.dilate(core, _ellipse(9))
    shadow = cv2.warpAffine(cv2.dilate(core, _ellipse(19)), np.float32([[1, 0, -9], [0, 1, -7]]), img.shape[1::-1])
    mask = (near | shadow) > 0
    mask &= ~(tree_pixels(img) & ~(cv2.dilate(core, _ellipse(5)) > 0))   # 露在外面的树冠不动
    return mask.astype(np.uint8) * 255


TREE = dict(x=95, top=95, bottom=205, axis=57)   # logo 左下的树冠范围和竖直中线（原图量出）


def tree_pixels(img):
    f = img.astype(float)
    g = (f[..., 1] > f[..., 2] + 25) & (f[..., 1] > f[..., 0] + 10)
    out = np.zeros(g.shape, bool)
    out[TREE['top']:TREE['bottom'], :TREE['x']] = g[TREE['top']:TREE['bottom'], :TREE['x']]
    return out


def mirror_tree(img, res, mask):
    """树冠右半边被 logo 盖住：把露出的左半边（连勾线和明暗）按中线镜像过去"""
    m = mask > 0
    crown = cv2.dilate(tree_pixels(img).astype(np.uint8), _ellipse(5)) > 0
    out = res.copy()
    c = TREE['axis']
    for y in range(TREE['top'], TREE['bottom']):
        for x in range(c, 2 * c):
            sx = 2 * c - x
            if m[y, x] and 0 <= sx and not m[y, sx] and crown[y, sx]:
                out[y, x] = img[y, sx]
    return out


def lama(sess, img, mask, x, y, n):
    """把 (x, y) 起边长 n 的正方形缩放到 512 修补，只把蒙版内的像素写回"""
    crop, mc = img[y:y + n, x:x + n], mask[y:y + n, x:x + n]
    up = cv2.resize(crop, (512, 512), interpolation=cv2.INTER_CUBIC if n < 512 else cv2.INTER_AREA)
    mu = cv2.dilate(cv2.resize(mc, (512, 512), interpolation=cv2.INTER_NEAREST), np.ones((3, 3), np.uint8))
    t = cv2.cvtColor(up, cv2.COLOR_BGR2RGB).astype(np.float32).transpose(2, 0, 1)[None] / 255
    names = [i.name for i in sess.get_inputs()]
    res = sess.run(None, {names[0]: t, names[1]: (mu > 0).astype(np.float32)[None, None]})[0][0].transpose(1, 2, 0)
    if res.max() <= 1.5:    # 有的导出版本输出 0~1
        res = res * 255
    res = cv2.cvtColor(np.clip(res, 0, 255).astype(np.uint8), cv2.COLOR_RGB2BGR)
    res = cv2.resize(res, (n, n), interpolation=cv2.INTER_AREA if n < 512 else cv2.INTER_CUBIC)
    out = img.copy()
    sub = out[y:y + n, x:x + n]
    sub[mc > 0] = res[mc > 0]
    return out


def flatten(img, filled, mask):
    """修补区域压成平涂色：颜色取蒙版外一圈原画的聚类中心（去掉勾线）"""
    m = mask > 0
    ring = (cv2.dilate(mask, np.ones((41, 41), np.uint8)) > 0) & ~m
    ring[260:], ring[:, 430:] = False, False
    px = img[ring].astype(np.float32)
    px = px[px.sum(1) > 200]
    _, _, cent = cv2.kmeans(px, 10, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.5),
                            5, cv2.KMEANS_PP_CENTERS)
    sm = cv2.medianBlur(cv2.pyrMeanShiftFiltering(filled, 12, 28), 7)
    flat = sm.reshape(-1, 3).astype(np.float32)
    q = cent[((flat[:, None] - cent[None]) ** 2).sum(2).argmin(1)].reshape(img.shape).astype(np.uint8)
    out = img.copy()
    out[m] = cv2.medianBlur(q, 9)[m]
    return out


def skyline(img, flat, mask):
    """天空与楼群的分界整理成台阶，天空按行取原图颜色，楼群平涂，分界加勾线"""
    m = mask > 0
    f = flat.astype(float)
    issky = ((f - SKY) ** 2).sum(2) < ((f - LAV) ** 2).sum(2)
    green = (f[..., 1] > f[..., 2] + 25) & (f[..., 1] > f[..., 0] + 10)   # 树，不覆盖
    xs = np.nonzero(m[:SKYLINE_ROWS].any(0))[0]
    ys = np.array([np.argmin(issky[:SKYLINE_ROWS, x]) if not issky[:SKYLINE_ROWS, x].all() else SKYLINE_ROWS
                   for x in xs], float)
    ys = median_filter(ys, size=21, mode='nearest')
    steps, start = ys.copy(), 0
    for i in range(1, len(xs) + 1):
        if i == len(xs) or abs(ys[i] - np.median(ys[start:i])) > 6:
            steps[start:i] = np.round(np.median(ys[start:i]))
            start = i
    skyrow, last = {}, SKY
    for y in range(SKYLINE_ROWS):
        row = img[y][~m[y] & (((img[y].astype(float) - SKY) ** 2).sum(1) < 2500)]
        last = skyrow[y] = np.median(row, 0) if len(row) > 5 else last
    out = flat.astype(float)
    for x, sy in zip(xs, steps.astype(int)):
        for y in range(SKYLINE_ROWS):
            if m[y, x]:
                if y < sy:
                    out[y, x] = skyrow[y]
                elif not green[y, x]:
                    out[y, x] = LAV
    line = np.zeros(m.shape, np.uint8)
    pts = [(int(x), int(y)) for x, y in zip(xs, steps)]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        cv2.line(line, (x0, y0), (x1, y0), 255, 1, cv2.LINE_AA)
        if y0 != y1:
            cv2.line(line, (x1, y0), (x1, y1), 255, 1, cv2.LINE_AA)
    a = (line.astype(float) / 255 * m)[..., None]
    a[SKYLINE_ROWS:] = 0
    return (out * (1 - a) + INK * a).astype(np.uint8)


GROUND = ((0, 168), (345, 202))         # 楼群与路面的分界（左端、右端），按原图两侧量出
ROAD_L = np.array([148, 148, 148.])     # 左侧马路灰
ROAD_R = np.array([214, 194, 198.])     # 右侧人行道淡紫灰
CARS_FROM = 196                         # 这一行以下保留 AI 补出的车顶


def lower(img, res, mask):
    """楼群下半截：平涂紫色到地面线，下面路面（左灰右淡紫灰渐变），地面线加勾线；
    车所在的最底几行保留修补结果"""
    m = mask > 0
    f = res.astype(float)
    (x0, g0), (x1, g1) = GROUND
    out = f.copy()
    H, W = m.shape
    for y in range(SKYLINE_ROWS, H):
        for x in np.nonzero(m[y])[0]:
            g = g0 + (g1 - g0) * (x - x0) / (x1 - x0)
            if y < g:
                out[y, x] = LAV
            elif y < CARS_FROM or f[y, x].sum() < 300 or (x < 150 and f[y, x, 2] < f[y, x, 1] + 40):
                # 车顶以上、车区里补出的深色斑块、左边红车一带不是红色的杂色，都铺路面
                t = min(max(x / x1, 0), 1)
                out[y, x] = ROAD_L * (1 - t) + ROAD_R * t
    # 地面线勾线（只画在蒙版里）
    line = np.zeros(m.shape, np.uint8)
    cv2.line(line, (x0, g0), (x1, g1), 255, 1, cv2.LINE_AA)
    a = (line.astype(float) / 255 * m)[..., None]
    out = out * (1 - a) + INK * a
    return out.astype(np.uint8)


# 中文 logo（“美女”比“Parking”短）露出了左上一大块，自动生成的台阶天际线太规整，
# 这里照原画远景楼的画法手工排三栋：平顶 + 檐口 + 烟囱、三角山墙、平顶 + 尖顶水塔
LEFT_BLOCK = (slice(0, 118), slice(0, 125))      # 重画范围（行, 列），只改蒙版内、非树冠的像素
def _rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


LEFT_BUILDINGS = [                              # 由远到近，后画的盖住先画的；每栋是几个多边形的并集，原图坐标
    [_rect(66, 34, 125, 200), _rect(84, 22, 96, 34), [(82, 22), (90, 14), (98, 22)]],   # 平顶 + 尖顶水塔
    [[(38, 44), (54, 31), (70, 44), (70, 200), (38, 200)]],                             # 三角山墙
    [_rect(6, 26, 40, 200), _rect(4, 23, 42, 27), _rect(24, 15, 31, 23)],               # 平顶 + 檐口 + 烟囱
]


def left_skyline(img, res, mask):
    """左上三栋楼：4 倍超采样画剪影和勾线再缩回，天空按行取原图颜色"""
    k = 4
    ys, xs = LEFT_BLOCK
    h, w = ys.stop - ys.start, xs.stop - xs.start
    lab = np.zeros((h * k, w * k), np.uint8)
    for i, parts in enumerate(LEFT_BUILDINGS, 1):
        for poly in parts:
            p = (np.array(poly, np.float32) - [xs.start, ys.start]) * k
            cv2.fillPoly(lab, [np.round(p).astype(np.int32)], i)
    edge = np.zeros(lab.shape, np.uint8)      # 勾线：天空/各栋楼之间的分界
    edge[1:] |= lab[1:] != lab[:-1]
    edge[:, 1:] |= lab[:, 1:] != lab[:, :-1]
    edge = cv2.dilate(edge, _ellipse(5))
    m = mask[ys, xs] > 0
    f = res[ys, xs].astype(float)
    green = (f[..., 1] > f[..., 2] + 25) & (f[..., 1] > f[..., 0] + 10)
    building = cv2.resize((lab > 0).astype(np.float32), (w, h), interpolation=cv2.INTER_AREA)[..., None]
    line = cv2.resize(edge.astype(np.float32), (w, h), interpolation=cv2.INTER_AREA)[..., None]
    sky = np.zeros_like(f)
    for y in range(h):
        row = img[ys.start + y][~(mask[ys.start + y] > 0) & (((img[ys.start + y].astype(float) - SKY) ** 2).sum(1) < 2500)]
        sky[y] = np.median(row, 0) if len(row) > 5 else SKY
    new = sky * (1 - building) + LAV * building
    new = new * (1 - line) + INK * line
    out = res.copy()
    sub = out[ys, xs]
    use = m & ~green
    sub[use] = new[use].astype(np.uint8)
    return out


CAR_ROOF = dict(                                # 米色掀背车车顶（参照 assets/cars/carfront46.png 的圆顶车厢）：
    left=((166, 194), (156, 207)),              # 用户在 PSD 图层 1 画的车顶左缘
    right=((210, 195), (225, 202)),             # 和右后缘；两线之间是车顶
    box=(slice(188, 210), slice(140, 240)),
    roof=np.array([156, 176, 180.]),            # BGR 车身米灰（取自原图露出的车身）
    patch=np.array([156, 171, 194.]),           # 要替换的粉棕色补丁
)


def car_roof(res, mask):
    """把米色车顶上方的粉棕色补丁按用户画的车顶线分成车身色和路面色"""
    c = CAR_ROOF
    (lx0, ly0), (lx1, ly1) = c['left']
    (rx0, ry0), (rx1, ry1) = c['right']
    out = res.copy()
    ys, xs = c['box']
    for y in range(ys.start, ys.stop):
        for x in range(xs.start, xs.stop):
            if not mask[y, x] or ((res[y, x].astype(float) - c['patch']) ** 2).sum() > 30 ** 2:
                continue
            xl = lx0 + (lx1 - lx0) * (y - ly0) / (ly1 - ly0)
            yr = ry0 + (ry1 - ry0) * (x - rx0) / (rx1 - rx0)
            if x > xl and (x < rx0 or y > yr):
                out[y, x] = c['roof']
            else:
                t = min(max(x / GROUND[1][0], 0), 1)
                out[y, x] = ROAD_L * (1 - t) + ROAD_R * t
    return out


PSD = os.path.join(HERE, 'welcomem_clean.psd')


def user_layer():
    """用户在 PSD「图层 1」手绘的内容（RGBA，800×600）；没有 PSD 时返回 None"""
    if not os.path.exists(PSD):
        return None
    from psd_tools import PSDImage
    for layer in PSDImage.open(PSD):
        if layer.name == '图层 1':
            return np.asarray(layer.composite(viewport=(0, 0, 800, 600)).convert('RGBA'))
    return None


TREE_TOP = dict(                                # 树冠顶部原先被字母 P 压着（还带着 logo 的投影）
    cols=(28, 95),                              # 以用户画的波浪形树冠轮廓为上沿
    bottom=126,                                 # 这一行以下是完好的原树冠（logo 投影到这里为止）
    shift=45,                                   # 纹理取自原图往下这么多行的树冠（避开投影）
    feather=4,
)


def tree_top(img, res, layer):
    """用户波浪线以下到 bottom 之间换成原图树冠的叶子纹理，下沿羽化接上原树冠。
    纹理只从原图露在外面的左半边树冠取（右半边按中线镜像过去取），因为右半边是补出来的。
    这里改的像素有些在蒙版外（被投影压暗的原树冠），所以要在最后还原蒙版外像素之后再做"""
    c = TREE_TOP
    dark = (layer[..., 3] > 100) & (layer[..., :3].astype(int).sum(2) < 300)   # 只认深色线条，不算紫色笔刷
    out = res.astype(float)
    src = img.astype(float)
    axis = TREE['axis']
    for x in range(*c['cols']):
        sx = x if x < axis else 2 * axis - x
        ys = np.nonzero(dark[84:c['bottom'] + 10, x])[0]
        if not len(ys):
            continue
        top = 84 + ys.min()
        for y in range(top, c['bottom'] + c['feather']):
            t = min(1.0, (c['bottom'] + c['feather'] - y) / c['feather'])   # 最后几行渐变回原树冠
            out[y, x] = src[y + c['shift'], sx] * t + out[y, x] * (1 - t)
    return out.astype(np.uint8)


RED_CAR = dict(                                 # logo 下的红色复古车（同款素材 assets/cars/carfront15.png，朝向一致）
    zone=(slice(205, 236), slice(70, 160)),
    glass=[(116, 225), (106, 227)],             # 两扇侧窗 → 玻璃色
    roof=((82, 215), (106, 209), (130, 212)),   # 车顶弧线（素材的圆顶车厢），弧线以上是路面
    red=np.array([97, 111, 197.]),              # BGR，取自原图露出的车身
    glass_col=np.array([213, 228, 221.]),       # BGR，取自素材车窗
)


def red_car(res, mask, lines):
    """按用户画的车厢线分区上色，补上车顶弧线"""
    c = RED_CAR
    ys, xs = c['zone']
    zone = np.zeros(mask.shape, bool)
    zone[ys, xs] = True
    f = res.astype(int)
    reddish = f[..., 2] > f[..., 1] + 40
    pink = (mask > 0) & ~lines & zone & reddish & (f[..., 0] > f[..., 1])   # 粉紫色补丁：分区时不算，最后并进车身
    cand = (mask > 0) & ~lines & zone & ~reddish
    n, lab = cv2.connectedComponents(cand.astype(np.uint8), connectivity=4)

    def comp(seed):
        x, y = seed
        win = lab[y - 3:y + 4, x - 3:x + 4]
        ids = win[win > 0]
        return np.bincount(ids).argmax() if len(ids) else 0
    (x0, y0), (x1, y1), (x2, y2) = c['roof']
    arc = np.polyfit([x0, x1, x2], [y0, y1, y2], 2)
    out = res.astype(float)
    yy, xx = np.mgrid[0:mask.shape[0], 0:mask.shape[1]]
    above = yy < np.polyval(arc, xx)
    glass_ids = [comp(s) for s in c['glass']]
    # 车窗以外、被车厢线分出的区块都算车身（右边 x≥140 那块是米色车旁的路面，不动）
    body_ids = [i for i in range(1, n) if i not in glass_ids and np.nonzero(lab == i)[1].mean() < 140]
    body = np.isin(lab, body_ids) | pink
    out[body & ~above] = c['red']
    t = np.clip(xx / GROUND[1][0], 0, 1)[..., None]
    road = ROAD_L * (1 - t) + ROAD_R * t
    out[body & above] = road[body & above]
    glass = np.isin(lab, glass_ids) & (lab > 0)
    out[glass] = c['glass_col']
    k = 4                                       # 车顶弧线：4 倍超采样画 1.5px 勾线
    pts = np.array([(x, np.polyval(arc, x)) for x in np.linspace(x0, x2, 40)]) * k
    line = np.zeros((mask.shape[0] * k, mask.shape[1] * k), np.uint8)
    cv2.polylines(line, [np.round(pts).astype(np.int32)], False, 255, 6, cv2.LINE_AA)
    a = cv2.resize(line, mask.shape[::-1], interpolation=cv2.INTER_AREA).astype(float) / 255
    a = (a * zone * (mask > 0))[..., None]
    return (out * (1 - a) + INK * a).astype(np.uint8)


RIGHT_BUILDING = dict(                          # “美女”右边、灰蓝高楼左侧那栋近处的楼（照用户画的檐口和楼角线）
    region=(slice(56, 142), slice(272, 352)),
    corner=327,                                 # 楼角竖线
    top=((272, 62), (327, 62), (348, 68)),      # 檐口上沿
    bottom=73,                                  # 檐口下沿
    cornice=np.array([222, 196, 196.]),         # BGR 檐口（比墙亮）
    front=np.array([218, 188, 185.]),           # 楼角左侧正面
    side=np.array([208, 175, 172.]),            # 楼角右侧侧面（接原图露出的墙色）
    bricks=[(282, 86), (298, 94), (312, 83), (292, 110), (316, 104), (304, 124),
            (334, 84), (340, 100), (332, 118), (286, 130)],   # 砖缝短线（原画墙面上的小笔触）
    brick_col=np.array([150, 122, 120.]),
)


def right_building(res, mask):
    """右侧楼：檐口以下平涂墙面，楼角两侧分两种明暗，加几处砖缝"""
    c = RIGHT_BUILDING
    ys, xs = c['region']
    (ax, ay), (bx, by), (cx, cy) = c['top']
    out = res.astype(float)
    for y in range(ys.start, ys.stop):
        for x in range(xs.start, xs.stop):
            if not mask[y, x]:
                continue
            top = ay + (by - ay) * (x - ax) / (bx - ax) if x < bx else by + (cy - by) * (x - bx) / (cx - bx)
            if y < top:
                continue
            out[y, x] = c['cornice'] if y < c['bottom'] else (c['front'] if x < c['corner'] else c['side'])
    k = 4
    line = np.zeros((mask.shape[0] * k, mask.shape[1] * k), np.uint8)
    for i, (x, y) in enumerate(c['bricks']):
        w = 5 if i % 2 else 4
        cv2.line(line, (x * k, y * k), ((x + w) * k, y * k), 255, 4, cv2.LINE_AA)
        cv2.line(line, ((x + w) * k, y * k), ((x + w) * k, (y + 2) * k), 255, 4, cv2.LINE_AA)
    a = cv2.resize(line, mask.shape[::-1], interpolation=cv2.INTER_AREA).astype(float) / 255
    a = (a * (mask > 0))[..., None]
    return (out * (1 - a) + c['brick_col'] * a).astype(np.uint8)


RIGHT_WINDOW = dict(                            # 右侧楼正面的窗：照搬原画右上粉色楼的窗（木框 + 窗台），缩小后换成本楼墙色
    src=(slice(49, 118), slice(569, 622)),      # 原图里那扇窗（含窗台）
    sill_from=101,                              # 窗台从这一行开始（和木框同色，只能按位置分）
    dst=(80, 297),                              # 贴到 (y, x)
    scale=0.47,
)


def right_window(img, res, mask):
    """原窗里粉橘色的墙面 / 窗洞按明暗换成本楼正面颜色，窗台换成稍亮的同色，木框、玻璃、勾线保持原样"""
    c = RIGHT_WINDOW
    win = img[c['src']].copy()
    hsv = cv2.cvtColor(win, cv2.COLOR_BGR2HSV).astype(float)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    green = (win[..., 1].astype(int) > win[..., 2] + 20)                 # 右上角露进来的路牌
    wall = ((h < 25) | (h > 165)) & (s < 150) & (v > 170) | green
    vw = np.median(v[wall & ~green])
    front = RIGHT_BUILDING['front']
    shade = np.clip(v / vw, 0, 1.15)[..., None]
    shade[green] = 1
    sill = np.zeros(wall.shape, bool)
    sill[c['sill_from'] - c['src'][0].start:] = True
    sill &= ((h < 25) | (h > 165)) & (s < 175) & (v > 170) & ~green
    vs = np.median(v[sill]) if sill.any() else vw
    sill_shade = np.clip(v / vs, 0, 1.15)[..., None]
    new = np.where(wall[..., None], front * shade, win)
    new = np.where(sill[..., None], np.minimum(front * 1.06, 255) * sill_shade, new)   # 窗台比墙面稍亮
    win = np.clip(new, 0, 255).astype(np.uint8)
    hh, ww = int(round(win.shape[0] * c['scale'])), int(round(win.shape[1] * c['scale']))
    win = cv2.resize(win, (ww, hh), interpolation=cv2.INTER_AREA)
    y, x = c['dst']
    out = res.copy()
    sub, m = out[y:y + hh, x:x + ww], mask[y:y + hh, x:x + ww] > 0
    sub[m] = win[m]
    return out


def main():
    img = cv2.imread(SRC)
    mask = make_mask(img)
    cv2.imwrite(MASK, mask)
    sess = ort.InferenceSession(MODEL, providers=['CPUExecutionProvider'])
    # 整图补一遍（下面补 200 行镜像凑成正方形，给模型完整上下文）
    big = cv2.copyMakeBorder(img, 0, 200, 0, 0, cv2.BORDER_REFLECT)
    bm = cv2.copyMakeBorder(mask, 0, 200, 0, 0, cv2.BORDER_CONSTANT, value=0)
    coarse = lama(sess, big, bm, 0, 0, 800)[:600]
    inner = cv2.erode(mask, _ellipse(41))
    filled = lama(sess, coarse, inner, 0, 0, 420)
    res = mirror_tree(img, lower(img, skyline(img, flatten(img, filled, mask), mask), mask), mask)
    res = right_building(car_roof(left_skyline(img, res, mask), mask), mask)
    res = right_window(img, res, mask)
    layer = user_layer()
    if layer is not None:
        res = red_car(res, mask, layer[..., 3] > 100)
    a = cv2.GaussianBlur((mask > 0).astype(np.float32), (0, 0), 1.5)
    a = np.maximum(a, mask > 0)[..., None]
    res = (res * a + img * (1 - a)).astype(np.uint8)
    if layer is not None:
        res = tree_top(img, res, layer)
    cv2.imwrite(OUT, res)
    print('已写出', OUT)


if __name__ == '__main__':
    main()
