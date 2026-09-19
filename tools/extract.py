# -*- coding: utf-8 -*-
"""Вырезает иллюстрации из правил «Орлеана» в папку img/ проекта."""
import os, io, pymupdf, numpy as np
from collections import deque
from PIL import Image, ImageDraw, ImageFilter

# Путь к правилам можно задать переменной окружения ORLEANS_PDF.
PDF = os.environ.get('ORLEANS_PDF', r'M:\Downloads\Orleans.pdf')
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'img')
os.makedirs(OUT, exist_ok=True)
doc = pymupdf.open(PDF)

def render(page, rect, dpi):
    pm = doc[page].get_pixmap(clip=pymupdf.Rect(*rect), dpi=dpi)
    return Image.frombytes('RGB', (pm.width, pm.height), pm.samples)

def biggest_blob(mask, frac=0.04):
    """Оставляет только крупные куски — мелкие крапины фона выбрасываются."""
    h, w = mask.shape
    seen = np.zeros((h, w), bool)
    blobs = []
    for sy in range(h):
        for sx in range(w):
            if not mask[sy, sx] or seen[sy, sx]: continue
            cur, q = [], deque([(sy, sx)]); seen[sy, sx] = True
            while q:
                y, x = q.popleft(); cur.append((y, x))
                for dy, dx in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
                    ny, nx = y+dy, x+dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True; q.append((ny, nx))
            blobs.append(cur)
    if not blobs: return mask
    big = max(len(b) for b in blobs)
    out = np.zeros((h, w), bool)
    for b in blobs:
        if len(b) >= big * frac:
            ys, xs = zip(*b); out[list(ys), list(xs)] = True
    return out

def strip_bg(im, tol=34):
    """Убирает фон-пергамент заливкой от краёв."""
    a = np.asarray(im, dtype=np.int16)
    h, w, _ = a.shape
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]]).astype(np.float64)
    seed = np.median(border, axis=0)
    close = (np.abs(a - seed).sum(axis=2) <= tol)
    out = np.zeros((h, w), bool)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if close[y, x] and not out[y, x]: out[y, x] = True; q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if close[y, x] and not out[y, x]: out[y, x] = True; q.append((y, x))
    while q:
        y, x = q.popleft()
        for dy, dx in ((1,0),(-1,0),(0,1),(0,-1)):
            ny, nx = y+dy, x+dx
            if 0 <= ny < h and 0 <= nx < w and close[ny, nx] and not out[ny, nx]:
                out[ny, nx] = True; q.append((ny, nx))
    keep = ~out
    keep = biggest_blob(keep)
    alpha = Image.fromarray(np.where(keep, 255, 0).astype(np.uint8), 'L')
    alpha = alpha.filter(ImageFilter.GaussianBlur(0.6)).point(lambda v: 0 if v < 90 else v)
    rgba = im.convert('RGBA'); rgba.putalpha(alpha)
    return rgba.crop(rgba.getbbox() or (0, 0, im.width, im.height))

def fit(im, size, pad=0):
    """Вписывает картинку в квадрат size×size, сохраняя пропорции."""
    k = min((size - pad * 2) / im.width, (size - pad * 2) / im.height)
    im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
    canvas = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    canvas.paste(im, ((size - im.width) // 2, (size - im.height) // 2))
    return canvas

def sharpen(im, percent=70):
    """Лёгкая резкость: оригиналы в правилах мелкие, после увеличения мылят."""
    rgb = im.convert('RGB').filter(ImageFilter.UnsharpMask(1.8, percent, 2))
    return Image.merge('RGBA', (*rgb.split(), im.getchannel('A')))

def masked(xref, smask):
    """Достаёт картинку вместе с её альфа-маской из PDF — контур получается точным,
    без заливки фона от краёв и без риска срезать обводку."""
    pm = pymupdf.Pixmap(pymupdf.Pixmap(doc, xref), pymupdf.Pixmap(doc, smask))
    im = Image.frombytes('RGBA', (pm.width, pm.height), pm.samples)
    bb = im.getchannel('A').getbbox()
    return im.crop(bb) if bb else im

def disc(xref, size, rim=4.5, ss=4):
    """Круглый жетон (монета): маски в PDF нет, зато форма — окружность,
    поэтому режем по ней со сглаживанием и возвращаем обводку, как в правилах."""
    im = Image.open(io.BytesIO(doc.extract_image(xref)['image'])).convert('RGB')
    out = im.resize((size, size), Image.LANCZOS).convert('RGBA')
    box = (ss, ss, size * ss - ss - 1, size * ss - ss - 1)
    m = Image.new('L', (size * ss,) * 2, 0)
    ImageDraw.Draw(m).ellipse(box, fill=255)
    out.putalpha(m.resize((size, size), Image.LANCZOS))
    ring = Image.new('RGBA', (size * ss,) * 2, (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse(box, outline=(26, 20, 12, 255), width=round(ss * rim))
    out.alpha_composite(ring.resize((size, size), Image.LANCZOS))
    return out

# --- жетоны товаров (стр. 3, рынок) и прочие значки (стр. 9, подсчёт очков) ---
CUT = 17.0
TOKENS = [('grain', 144.35), ('cheese', 180.45), ('wine', 215.95), ('wool', 251.45), ('brocade', 287.35)]
for name, cx in TOKENS:
    im = render(2, (cx - CUT, 421.65 - CUT, cx + CUT, 421.65 + CUT), 560)
    fit(strip_bg(im), 160).save(f'{OUT}/{name}.png')
    print(name, 'ok')

# Фактория и звезда развития лежат в PDF со своими альфа-масками — берём их
# оттуда: контур выходит целым, тогда как вырезание с отрендеренной страницы
# срезало фактории правый бок, а звезде оставляло серый ореол.
for name, xref, smask, pad in [('station', 689, 690, 4), ('star', 691, 692, 2)]:
    sharpen(fit(masked(xref, smask), 160, pad)).save(f'{OUT}/{name}.png')
    print(name, 'ok')

sharpen(disc(687, 160)).save(f'{OUT}/coin.png')          # монета — маски нет, режем по кругу
print('coin ok')

sharpen(fit(strip_bg(render(8, (440, 491, 478, 539), 560)), 160, 2)).save(f'{OUT}/citizen.png')
print('citizen ok')

# --- тайлы производств (стр. 10) — крупная «шапка» для каждого товара ---
PLACES = [('grain', 38.0, 107.6), ('cheese', 111.8, 181.7), ('wine', 184.3, 254.8),
          ('wool', 257.6, 328.1), ('brocade', 331.8, 402.2)]
for name, x0, x1 in PLACES:
    im = render(9, (x0, 726.8, x1, 797.6), 620).convert('RGB')
    im.save(f'{OUT}/tile-{name}.jpg', quality=88, optimize=True)
    print('tile-' + name, im.size)

# --- обложка (для превью в соцсетях) и фон-пергамент ---
cov = Image.open(io.BytesIO(doc.extract_image(14)['image'])).convert('RGB')
w, h = cov.size
cov.resize((600, int(600 * h / w)), Image.LANCZOS).save(f'{OUT}/cover.jpg', quality=80, optimize=True)
print('cover', cov.size)

bg = Image.open(io.BytesIO(doc.extract_image(10)['image'])).convert('RGB')
W, H = bg.size
bg.crop((int(W*.10), int(H*.12), int(W*.62), int(H*.88))).resize((760, 760), Image.LANCZOS)\
  .save(f'{OUT}/parchment.jpg', quality=78, optimize=True)
print('parchment ok')

# --- значок сайта: буква «О» с лилией из обложки ---
O = strip_bg(cov.crop((70, 28, 456, 458)), tol=96)
O.putalpha(O.getchannel('A').filter(ImageFilter.MinFilter(3)))
O = O.crop(O.getbbox())
side = 500
icon = Image.new('RGB', (side, side), (238, 223, 189))
O2 = O.copy(); O2.thumbnail((side - 56, side - 56), Image.LANCZOS)
icon.paste(O2, ((side - O2.width) // 2, (side - O2.height) // 2), O2)
icon.resize((256, 256), Image.LANCZOS).quantize(colors=128, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG)\
    .save(f'{OUT}/icon.png', optimize=True)
print('icon ok')
