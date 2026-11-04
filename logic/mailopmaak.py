"""
Opmaak van de rapportmails (dagrapport, weekrapport, Teelt afgerond): tegels met kengetallen, staafgrafiekjes en
tabellen, in één stijl. Alleen HTML-tabellen met inline stijl, geen plaatjes, CSS-variabelen of flexbox, zodat het
in Outlook, Gmail en op een telefoon hetzelfde oogt en er geen bijlagen nodig zijn. Tests in tests/test_mailopmaak.py.
"""
import html
from datetime import date

from utils.format import LEEG, fmt_getal, fmt_verschil

GROEN, GRIJS, LICHT, RAND = "#2E6A4C", "#6f6f6a", "#f3f5f1", "#e3e3e0"
ORANJE, ROOD, BLAUW, STIL = "#d68910", "#c0392b", "#2e75b6", "#b9c4bb"
FONT = "font-family:Arial,Helvetica,sans-serif"
MAAND = ("jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec")


def e(tekst):
    return html.escape(str(tekst))


def omhulsel(inhoud, breedte=760):
    """Het geheel van de mail: lettertype, tekstkleur en maximale breedte."""
    return f'<div style="{FONT};font-size:13px;color:#1f1f1f;max-width:{breedte}px">{inhoud}</div>'


def kop(titel, onder=None):
    return (f'<h2 style="{FONT};color:{GROEN};margin:0 0 2px;font-size:20px">{e(titel)}</h2>'
            + (f'<div style="color:{GRIJS};font-size:12px;margin-bottom:10px">{e(onder)}</div>' if onder else ""))


def sectiekop(tekst, klein=False):
    grootte = "13px" if klein else "15px"
    return (f'<h3 style="{FONT};color:{GROEN};margin:18px 0 4px;font-size:{grootte};border-bottom:1px solid {RAND};'
            f'padding-bottom:2px">{e(tekst)}</h3>')


def voetnoot(tekst):
    return f'<p style="color:{GRIJS};font-size:11px;margin:6px 0">{tekst}</p>'


# --- Tegels ---

def tegels(rij, label=None, breedte=6):
    """
    Een rij tegels (kengetallen). rij: [{label, waarde, eenheid, sub, toon}]; toon "let op" (oranje) of "fout" (rood)
    kleurt de waarde. label: een kopje links boven de rij (bijv. de tuin). Meer dan `breedte` tegels lopen door op
    een tweede rij.
    """
    uit = []
    if label:
        uit.append(f'<div style="{FONT};font-weight:bold;font-size:12px;margin:10px 0 2px;color:#1f1f1f">{e(label)}</div>')
    for begin in range(0, len(rij), breedte):
        deel = rij[begin:begin + breedte]
        cellen = []
        for t in deel:
            kleur = {"let op": ORANJE, "fout": ROOD}.get(t.get("toon"), "#1f1f1f")
            eenheid = f' <span style="font-size:11px;color:{GRIJS};font-weight:normal">{e(t["eenheid"])}</span>' \
                if t.get("eenheid") and t["waarde"] != LEEG else ""
            sub = f'<div style="font-size:10px;color:{GRIJS};margin-top:1px">{e(t["sub"])}</div>' if t.get("sub") \
                else '<div style="font-size:10px">&nbsp;</div>'
            cellen.append(
                f'<td width="{100 // breedte}%" valign="top" style="background:{LICHT};border:3px solid #ffffff;'
                f'padding:6px 8px"><div style="font-size:10px;color:{GRIJS}">{e(t["label"])}</div>'
                f'<div style="font-size:18px;font-weight:bold;color:{kleur};margin-top:1px">{e(t["waarde"])}{eenheid}'
                f"</div>{sub}</td>")
        cellen += [f'<td width="{100 // breedte}%"></td>'] * (breedte - len(deel))
        uit.append(f'<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;{FONT}">'
                   f'<tr>{"".join(cellen)}</tr></table>')
    return "".join(uit)


def verschil_tekst(nu, toen, decimalen=1, eenheid=""):
    """Het verschil met de vorige periode als "+0,3 °C", of None zonder vergelijking."""
    if nu is None or toen is None or nu != nu or toen != toen:
        return None
    return fmt_verschil(nu - toen, decimalen, eenheid)


# --- Staafgrafiekjes ---

def _dagnaam(d):
    return f"{d.day} {MAAND[d.month - 1]}"


def _balk(hoogte, kleur):
    """Eén balk: een tabel van één cel (Outlook kent de hoogte van een td, niet van een div)."""
    if hoogte <= 0:
        return "&nbsp;"
    return (f'<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse"><tr>'
            f'<td height="{hoogte}" bgcolor="{kleur}" style="height:{hoogte}px;background:{kleur};font-size:1px;'
            f'line-height:1px">&nbsp;</td></tr></table>')


def staafgrafiek(titel, dagen, rijen, kleur, eenheid="", decimalen=0, minimum=1.0, uitleg=None, hoogte=34,
                 tweezijdig=False, breedte=34):
    """
    Een staafgrafiekje per dag, een rij per reeks (bijv. per tuin).
    dagen: [date]; rijen: [(naam, [waarde of None per dag])]; kleur(waarde) → kleur van de balk.
    tweezijdig: ook negatieve waarden (balk naar beneden), bijv. de afwijking van de lichtlijn.
    Alle rijen delen één schaal (minstens `minimum`), zodat tuinen vergelijkbaar zijn. Achter elke rij de laatste
    waarde; `uitleg` is de regel onder de titel.
    """
    alle = [abs(v) if tweezijdig else v for _, waarden in rijen for v in waarden if v is not None]
    schaal = max([minimum] + alle)
    n = len(dagen)
    dagbreedte = breedte if n <= 14 else max(10, breedte * 14 // n)
    stap = 1 if n <= 14 else 7

    def eenheid_hoogte(v):
        return int(round(abs(v) / schaal * hoogte)) if v else 0

    uit = [f'<div style="{FONT};font-weight:bold;font-size:12px;margin:12px 0 0">{e(titel)}</div>']
    if uitleg:
        uit.append(f'<div style="{FONT};color:{GRIJS};font-size:11px;margin-bottom:3px">{e(uitleg)}</div>')
    tabel = [f'<table cellpadding="0" cellspacing="0" style="border-collapse:collapse;{FONT}">']
    for naam, waarden in rijen:
        laatste = next((v for v in reversed(waarden) if v is not None), None)
        laatste_tekst = (fmt_verschil(laatste, decimalen) if tweezijdig else fmt_getal(laatste, decimalen)) \
            if laatste is not None else LEEG
        boven, onder = [], []
        for d, v in zip(dagen, waarden):
            waarde = LEEG if v is None else (fmt_verschil(v, decimalen) if tweezijdig else fmt_getal(v, decimalen))
            hint = f"{_dagnaam(d)}: {waarde}" + (f" {eenheid}" if eenheid and v is not None else "")
            if v is None:
                bar_boven, bar_onder = _balk(1, STIL) if not tweezijdig else "&nbsp;", "&nbsp;"
            elif tweezijdig and v < 0:
                bar_boven, bar_onder = "&nbsp;", _balk(max(eenheid_hoogte(v), 1), kleur(v))
            else:
                bar_boven, bar_onder = _balk(max(eenheid_hoogte(v), 1 if v else 0), kleur(v)), "&nbsp;"
            rand = f"border-bottom:1px solid {STIL};" if tweezijdig else ""
            boven.append(f'<td title="{e(hint)}" valign="bottom" width="{dagbreedte}" style="height:{hoogte}px;'
                         f'padding:0 1px;{rand}">{bar_boven}</td>')
            onder.append(f'<td title="{e(hint)}" valign="top" width="{dagbreedte}" style="height:{hoogte}px;'
                         f'padding:0 1px">{bar_onder}</td>')
        rijen_span = 2 if tweezijdig else 1
        tabel.append(f'<tr><td rowspan="{rijen_span}" valign="middle" style="padding-right:8px;font-size:11px;'
                     f'white-space:nowrap">{e(naam)}</td>{"".join(boven)}<td rowspan="{rijen_span}" valign="middle" '
                     f'style="padding-left:8px;font-size:12px;font-weight:bold;white-space:nowrap">'
                     f"{e(laatste_tekst)}</td></tr>")
        if tweezijdig:
            tabel.append(f'<tr>{"".join(onder)}</tr>')
    # Onderaan de dagen: de laatste en om de 7 dagen terug.
    labels = [f'<td style="font-size:10px;color:{GRIJS};text-align:center;white-space:nowrap">'
              f'{e(_dagnaam(d)) if (n - 1 - i) % stap == 0 else ""}</td>' for i, d in enumerate(dagen)]
    tabel.append(f'<tr><td></td>{"".join(labels)}<td></td></tr></table>')
    uit.append("".join(tabel))
    return "".join(uit)


# --- Tabellen ---

def tabel(koppen, rijen, eerste_links=1, klein=False):
    """rijen: lijst dicts met tekst per kop, of lijsten in de volgorde van de koppen."""
    grootte = "11px" if klein else "12px"
    stijl_kop = (f"padding:3px 8px;border-bottom:2px solid {GROEN};text-align:{{}};white-space:nowrap;font-size:{grootte}")
    stijl_cel = (f"padding:3px 8px;border-bottom:1px solid {RAND};text-align:{{}};white-space:nowrap;font-size:{grootte}")
    kop_ = "".join(f'<th style="{stijl_kop.format("left" if i < eerste_links else "right")}">{e(k)}</th>'
                   for i, k in enumerate(koppen))
    body = []
    for rij in rijen:
        cellen = [rij.get(k, "") for k in koppen] if isinstance(rij, dict) else rij
        body.append("<tr>" + "".join(
            f'<td style="{stijl_cel.format("left" if i < eerste_links else "right")}">{e(w)}</td>'
            for i, w in enumerate(cellen)) + "</tr>")
    return (f'<table style="border-collapse:collapse;{FONT}"><tr>{kop_}</tr>{"".join(body)}</table>')
