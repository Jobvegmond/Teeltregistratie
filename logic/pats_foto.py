"""
Wat er tussen twee foto's van een vangplaat (Trap-Eye) bij is gekomen. Alleen beeldrekenwerk (numpy en Pillow);
de app haalt de foto's op (integrations/pats.py). Tests in tests/test_pats_foto.py.

PATS telt per foto het aantal nieuwe trips, witte vliegen en mineervliegen, maar geeft niet door wáár ze zitten (de
foto met kaders vraagt een extra recht). Daarom vergelijken we de foto met de vorige foto van dezelfde plaat:
- beide foto's naar "donkerte" (hoeveel donkerder dan de plaat zelf, de mediaan), zodat een andere belichting
  weinig uitmaakt;
- de vorige foto over de nieuwe leggen (verschuiving via fasecorrelatie op een verkleinde foto);
- nieuw = op de nieuwe foto donker, terwijl er op de vorige foto in een buurt van 15 × 15 pixels niets was (zo telt
  een insect dat een paar pixels verschuift of een kleine scheefstand niet als nieuw);
- aaneengesloten vlekken op halve resolutie, met hun midden en grootte.
Wat nieuw is, is dus álles wat erbij kwam (ook vliegjes die PATS niet telt); de kleinste vlekken staan vooraan,
want daar zitten de trips tussen. Bij een nieuwe plaat (alles is nieuw) heeft de vergelijking geen zin.
"""
import io

import numpy as np
from PIL import Image, ImageDraw

RAND = 120              # pixels langs de rand van de foto die niet meetellen (het zwarte kader en de houder)
DREMPEL = 35            # zoveel donkerder dan de vorige foto (0–255) = nieuw
BUURT = 15              # tolerantie voor verschuiven, in pixels
MIN_PIXELS = 4          # kleinste vlek, in pixels op halve resolutie
UITSNEDE = 40           # halve breedte van een uitsnede rond een nieuwe vlek, in pixels
VERGROTING = 160        # breedte van een uitsnede in beeld


def open_foto(data):
    """JPEG-bytes (of een PIL-beeld) → RGB-beeld."""
    return data.convert("RGB") if isinstance(data, Image.Image) else Image.open(io.BytesIO(data)).convert("RGB")


def donkerte(beeld):
    """Per pixel hoeveel donkerder dan de plaat (de mediaan van de foto), 0..255 als float-array."""
    g = np.asarray(beeld.convert("L")).astype(float)
    return np.clip(np.median(g) - g, 0, 255)


def verschuiving(nieuw, oud, stap=4):
    """(dy, dx) waarmee `oud` over `nieuw` valt (fasecorrelatie op elke `stap`-de pixel), in hele pixels."""
    a, b = nieuw[::stap, ::stap], oud[::stap, ::stap]
    h, w = min(a.shape[0], b.shape[0]), min(a.shape[1], b.shape[1])
    a, b = a[:h, :w], b[:h, :w]
    f = np.fft.fft2(a) * np.conj(np.fft.fft2(b))
    f /= np.abs(f) + 1e-9
    c = np.fft.ifft2(f).real
    y, x = np.unravel_index(int(c.argmax()), c.shape)
    dy, dx = (y - h if y > h // 2 else y), (x - w if x > w // 2 else x)
    return dy * stap, dx * stap


def _max_buurt(a, n):
    """Per pixel het maximum in een buurt van n × n (n oneven), per as apart; de rand telt als 0."""
    for as_ in (0, 1):
        uit = a.copy()
        for d in range(1, n // 2 + 1):
            for stap in (d, -d):
                schuif = np.roll(a, stap, axis=as_)
                rand = [slice(None)] * 2
                rand[as_] = slice(0, stap) if stap > 0 else slice(stap, None)
                schuif[tuple(rand)] = 0
                np.maximum(uit, schuif, out=uit)
        a = uit
    return a


def vlekken(masker):
    """Aaneengesloten vlekken (4-buren) in een bool-array: [(pixels, x, y, breedte, hoogte)], x/y = het midden."""
    h, w = masker.shape
    gezien = np.zeros_like(masker, dtype=bool)
    uit = []
    for y0, x0 in zip(*np.nonzero(masker)):
        if gezien[y0, x0]:
            continue
        gezien[y0, x0] = True
        stapel, xs, ys = [(y0, x0)], [], []
        while stapel:
            y, x = stapel.pop()
            xs.append(x)
            ys.append(y)
            for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= yy < h and 0 <= xx < w and masker[yy, xx] and not gezien[yy, xx]:
                    gezien[yy, xx] = True
                    stapel.append((yy, xx))
        uit.append((len(xs), int(round(np.mean(xs))), int(round(np.mean(ys))),
                    int(max(xs) - min(xs) + 1), int(max(ys) - min(ys) + 1)))
    return uit


def nieuwe_vlekken(voor, na):
    """
    Wat er op foto `na` bij is gekomen ten opzichte van foto `voor` (beelden of JPEG-bytes):
    [{x, y, breedte, hoogte, pixels}] in pixels van de volle foto, klein → groot.
    """
    voor, na = open_foto(voor), open_foto(na)
    if voor.size != na.size:
        voor = voor.resize(na.size)
    d_na, d_voor = donkerte(na), donkerte(voor)
    dy, dx = verschuiving(d_na, d_voor)
    d_voor = np.roll(np.roll(d_voor, dy, axis=0), dx, axis=1)
    nieuw = (d_na - _max_buurt(d_voor, BUURT)) > DREMPEL
    r = min(RAND, nieuw.shape[0] // 4, nieuw.shape[1] // 4)
    nieuw[:r, :] = nieuw[-r:, :] = False
    nieuw[:, :r] = nieuw[:, -r:] = False
    half = nieuw[::2, ::2]
    uit = [{"x": x * 2, "y": y * 2, "breedte": b * 2, "hoogte": h * 2, "pixels": n * 4}
           for n, x, y, b, h in vlekken(half) if n >= MIN_PIXELS]
    return sorted(uit, key=lambda v: (v["pixels"], v["y"], v["x"]))


def uitsnede(voor, na, vlek):
    """Eén beeld: boven de plek op de vorige foto, onder dezelfde plek op de nieuwe foto (vergroot)."""
    voor, na = open_foto(voor), open_foto(na)
    x, y, u = vlek["x"], vlek["y"], UITSNEDE
    vak = (x - u, y - u, x + u, y + u)
    beeld = Image.new("RGB", (VERGROTING, 2 * VERGROTING + 4), "white")
    beeld.paste(voor.crop(vak).resize((VERGROTING, VERGROTING), Image.LANCZOS), (0, 0))
    beeld.paste(na.crop(vak).resize((VERGROTING, VERGROTING), Image.LANCZOS), (0, VERGROTING + 4))
    return beeld


def gemarkeerd(na, vlekken_lijst, breedte=960):
    """De nieuwe foto verkleind tot `breedte`, met een genummerde rode ring om elke nieuwe vlek (nummer = volgorde)."""
    beeld = open_foto(na)
    schaal = breedte / beeld.width
    beeld = beeld.resize((breedte, round(beeld.height * schaal)), Image.LANCZOS)
    teken = ImageDraw.Draw(beeld)
    for i, v in enumerate(vlekken_lijst, 1):
        x, y = v["x"] * schaal, v["y"] * schaal
        r = max(14, max(v["breedte"], v["hoogte"]) * schaal / 2 + 6)
        teken.ellipse((x - r, y - r, x + r, y + r), outline=(220, 0, 0), width=3)
        teken.text((x + r + 2, y - r - 2), str(i), fill=(220, 0, 0), font_size=26)
    return beeld


def vorig_moment(momenten, dag):
    """
    (vorige, deze) fotomoment bij een teldag (date) uit een gesorteerde lijst "YYYYMMDD_HHMMSS"; deze = de laatste
    foto van die dag, vorige = de laatste foto van een eerdere dag (soms zijn er twee foto's op één dag). None als er
    op die dag geen foto is; vorige None als er geen eerdere dag is.
    """
    dag_tekst = f"{dag:%Y%m%d}"
    van_dag = [m for m in momenten if m.startswith(dag_tekst)]
    if not van_dag:
        return None
    eerder = [m for m in momenten if m[:8] < dag_tekst]
    return (eerder[-1] if eerder else None), van_dag[-1]
