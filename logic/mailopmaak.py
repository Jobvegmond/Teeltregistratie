"""
Opmaak van de rapportmails (dagrapport, weekrapport, Teelt afgerond): een kop, tegels met kengetallen, kaarten voor de
aandachtspunten, staafgrafiekjes en tabellen, in één stijl. E-mailclients zijn streng, dus: geneste tabellen met
role="presentation", alles inline, geen flexbox, grid, position, float of plaatjes; alleen een <style>-blok voor het
smalle scherm en de donkere stand (clients die dat negeren, zoals Outlook, tonen gewoon de inline opmaak).
Tests in tests/test_mailopmaak.py.
"""
import html

from utils.format import LEEG, fmt_getal, fmt_verschil

GROEN, GRIJS, LICHT, RAND = "#1F5E3B", "#6B7280", "#F4F6F4", "#E3E7E3"
ORANJE, ROOD, BLAUW, STIL = "#E67E22", "#C62828", "#1E6FB8", "#B9C4BB"
TEKST, PAGINA = "#222222", "#F4F6F4"
FONT = "font-family:-apple-system,'Segoe UI',Arial,sans-serif"
MAAND = ("jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec")
BASIS = 14                      # px: lopende tekst; tabellen en kleine regels zijn 13 en 12

STIJL = f"""
@media screen and (max-width:480px) {{
  .kaart {{ width:100% !important; }}
  .romp {{ padding:8px 14px 20px 14px !important; }}
  table.tegel {{ width:50% !important; }}
  .scroll {{ overflow-x:auto !important; }}
}}
@media (prefers-color-scheme:dark) {{
  .pagina {{ background:#101412 !important; }}
  .kaart {{ background:#1B201D !important; color:#E6EBE7 !important; }}
  .vlak {{ background:#252C28 !important; }}
  td.tegel {{ border-color:#1B201D !important; }}
  .zebra {{ background:#222824 !important; }}
  .titel {{ color:#8FD1A8 !important; }}
  .grijs {{ color:#A3ABA5 !important; }}
  .rand {{ border-color:#38413B !important; }}
  a {{ color:#8FD1A8 !important; }}
}}
"""


def e(tekst):
    return html.escape(str(tekst))


def omhulsel(inhoud, breedte=640, kop=None, titel="Rapport"):
    """
    Het geheel van de mail: een compleet HTML-document met de pagina (lichtgrijs), de kaart (wit, midden, maximaal
    `breedte` px), bovenaan de `kop` over de volle breedte en daaronder de inhoud met ruime marges.
    """
    return (
        '<!DOCTYPE html><html lang="nl"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="color-scheme" content="light dark"><meta name="supported-color-schemes" content="light dark">'
        f"<title>{e(titel)}</title><style>{STIJL}</style></head>"
        f'<body style="margin:0;padding:0;background:{PAGINA}">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" class="pagina" '
        f'bgcolor="{PAGINA}" style="background:{PAGINA}"><tr><td align="center" style="padding:16px 8px">'
        f'<table role="presentation" width="{breedte}" cellpadding="0" cellspacing="0" border="0" class="kaart" '
        f'bgcolor="#ffffff" style="table-layout:fixed;width:{breedte}px;max-width:100%;background:#ffffff;color:{TEKST};{FONT};'
        f'font-size:{BASIS}px;line-height:1.5">'
        f'{kop or ""}<tr><td class="romp" style="padding:8px 24px 24px 24px">{inhoud}</td></tr></table>'
        "</td></tr></table></body></html>")


def kop(titel, onder=None):
    """De donkergroene balk bovenaan: titel en eronder de periode (rijen van de kaart-tabel)."""
    return (f'<tr><td bgcolor="{GROEN}" style="background:{GROEN};padding:20px 24px;{FONT};color:#ffffff">'
            f'<div style="font-size:22px;font-weight:bold;line-height:1.3;color:#ffffff">{e(titel)}</div>'
            + (f'<div style="font-size:14px;color:#D5E6DB;padding-top:2px">{e(onder)}</div>' if onder else "")
            + "</td></tr>")


def sectiekop(tekst, klein=False):
    grootte = BASIS if klein else 18
    return (f'<div class="titel rand" style="{FONT};color:{GROEN};font-size:{grootte}px;font-weight:bold;'
            f'padding:{16 if klein else 24}px 0 4px;border-bottom:1px solid {RAND};margin-bottom:8px">{e(tekst)}</div>')


def voetnoot(tekst):
    return f'<div class="grijs" style="color:{GRIJS};font-size:12px;line-height:1.5;padding:6px 0">{tekst}</div>'


def alinea(tekst, vet=False):
    return f'<div style="font-size:{BASIS}px;padding:6px 0;{"font-weight:bold;" if vet else ""}">{e(tekst)}</div>'


# --- Tegels ---

def pijl(verschil):
    """"+0,3" → "▲ +0,3", "−0,3" → "▼ −0,3"; zonder teken (0,0 of leeg) ongewijzigd."""
    if not verschil:
        return verschil
    return "▲ " + verschil if verschil[0] == "+" else "▼ " + verschil if verschil[0] == "−" else verschil


def tegels(rij, label=None, breedte=4):
    """
    Tegels met kengetallen, `breedte` naast elkaar; ze zijn even hoog, dus ze lopen vanzelf door op een volgende
    rij. rij: [{label, waarde, eenheid, sub, toon}]; toon "let op" (oranje) of "fout" (rood) kleurt de waarde.
    label: een kopje boven de tegels (bijv. de tuin). Op een smal scherm staan er twee naast elkaar.
    """
    uit = []
    if label:
        uit.append(f'<div style="font-weight:bold;font-size:{BASIS}px;padding:12px 0 2px">{e(label)}</div>')
    cellen = []
    for t in rij:
        kleur = {"let op": ORANJE, "fout": ROOD}.get(t.get("toon"), "inherit")
        eenheid = (f' <span class="grijs" style="font-size:13px;color:{GRIJS};font-weight:normal">{e(t["eenheid"])}'
                   "</span>" if t.get("eenheid") and t["waarde"] != LEEG else "")
        sub = (f'<div class="grijs" style="font-size:12px;color:{GRIJS};padding-top:2px">{e(t["sub"])}</div>'
               if t.get("sub") else '<div style="font-size:12px">&nbsp;</div>')
        cellen.append(
            f'<table role="presentation" align="left" class="tegel" width="{100 // breedte}%" cellpadding="0" '
            f'cellspacing="0" border="0" style="width:{100 // breedte}%"><tr>'
            f'<td class="tegel vlak" valign="top" height="100" bgcolor="{LICHT}" style="background:{LICHT};'
            f'border:4px solid #ffffff;padding:8px 10px;height:100px"><div class="grijs" style="font-size:12px;'
            f'color:{GRIJS}">{e(t["label"])}</div><div style="font-size:22px;font-weight:bold;color:{kleur};'
            f'line-height:1.3">{e(t["waarde"])}{eenheid}</div>{sub}</td></tr></table>')
    uit.append(f'<div>{"".join(cellen)}<div style="clear:both;font-size:1px;line-height:1px">&nbsp;</div></div>')
    return "".join(uit)


def verschil_tekst(nu, toen, decimalen=1, eenheid=""):
    """Het verschil met de vorige periode als "+0,3 °C", of None zonder vergelijking."""
    if nu is None or toen is None or nu != nu or toen != toen:
        return None
    return fmt_verschil(nu - toen, decimalen, eenheid)


# --- Kaarten (aandachtspunten) ---

def badge(tekst, kleur):
    return (f'<span style="background:{kleur};color:#ffffff;font-size:11px;font-weight:bold;padding:2px 8px;'
            f'letter-spacing:0.5px">{e(tekst.upper())}</span>')


def kaart(kleur, soort, titel, tekst, plaats=None, actie=None, feedback_url=None):
    """
    Eén aandachtspunt: gekleurde linkerrand, badge (soort), tuin/afdeling als label, vette titel, uitleg, de actie op
    een eigen regel en rechtsonder een rustig knopje Feedback.
    """
    knop = (f'<table role="presentation" align="right" cellpadding="0" cellspacing="0" border="0"><tr>'
            f'<td class="rand" style="border:1px solid {RAND};padding:3px 12px"><a href="{e(feedback_url)}" '
            f'style="color:{GROEN};font-size:12px;text-decoration:none">Feedback</a></td></tr></table>'
            if feedback_url else "")
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="border-collapse:collapse;margin:0"><tr>'
        f'<td width="4" bgcolor="{kleur}" style="width:4px;background:{kleur};font-size:1px;line-height:1px">'
        f"&nbsp;</td>"
        f'<td class="vlak" bgcolor="{LICHT}" style="background:{LICHT};padding:12px 16px">'
        f'<div style="padding-bottom:4px">{badge(soort, kleur)}'
        + (f' <span class="grijs" style="color:{GRIJS};font-size:12px">&nbsp;{e(plaats)}</span>' if plaats else "")
        + f'</div><div style="font-size:15px;font-weight:bold;line-height:1.4">{e(titel)}</div>'
        f'<div style="font-size:{BASIS}px;padding-top:2px">{e(tekst)}</div>'
        + (f'<div style="font-size:{BASIS}px;padding-top:6px"><b>Actie:</b> {e(actie)}</div>' if actie else "")
        + (f'<div style="padding-top:8px;text-align:right">{knop}<div style="clear:both;font-size:1px">&nbsp;'
           "</div></div>" if knop else "")
        + '</td></tr></table><div style="font-size:1px;line-height:10px">&nbsp;</div>')


def regels(groepen):
    """
    Compacte lijst van controles. groepen: [(kopje, [(kleur, plaats, tekst)])]: per kopje een regel met een gekleurd
    blokje, de plaats (tuin, vak) en de tekst, gescheiden door een lijn onder elke rij.
    """
    uit = []
    for kopje, items in groepen:
        rijen = "".join(
            f'<tr><td class="rand" valign="top" width="8" style="padding:6px 0;border-bottom:1px solid {RAND}">'
            f'<span style="color:{kleur};font-size:13px">&#9632;</span></td>'
            f'<td class="rand grijs" valign="top" style="padding:6px 8px;border-bottom:1px solid {RAND};font-size:13px;'
            f'color:{GRIJS};white-space:nowrap">{e(plaats)}</td>'
            f'<td class="rand" valign="top" style="padding:6px 0;border-bottom:1px solid {RAND};font-size:13px">'
            f"{e(tekst)}</td></tr>" for kleur, plaats, tekst in items)
        uit.append(f'<div style="font-weight:bold;font-size:13px;padding:10px 0 0">{e(kopje)} ({len(items)})</div>'
                   f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
                   f'style="border-collapse:collapse">{rijen}</table>')
    return "".join(uit)


# --- Staafgrafiekjes ---

def _dagnaam(d):
    return f"{d.day} {MAAND[d.month - 1]}"


def _balk(hoogte, kleur):
    """Eén balk: een tabel van één cel (Outlook kent de hoogte van een td, niet van een div)."""
    if hoogte <= 0:
        return "&nbsp;"
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="border-collapse:collapse"><tr>'
            f'<td height="{hoogte}" bgcolor="{kleur}" style="height:{hoogte}px;background:{kleur};font-size:1px;'
            f'line-height:1px">&nbsp;</td></tr></table>')


def staafgrafiek(titel, dagen, rijen, kleur, eenheid="", decimalen=0, minimum=1.0, uitleg=None, hoogte=34,
                 tweezijdig=False, breedte=30):
    """
    Een staafgrafiekje per dag, een rij per reeks (bijv. per tuin).
    dagen: [date]; rijen: [(naam, [waarde of None per dag])]; kleur(waarde) → kleur van de balk.
    tweezijdig: ook negatieve waarden (balk naar beneden), bijv. het verschil tussen de tuinen.
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

    uit = [f'<div style="font-weight:bold;font-size:{BASIS}px;padding:14px 0 0">{e(titel)}</div>']
    if uitleg:
        uit.append(f'<div class="grijs" style="color:{GRIJS};font-size:12px;padding-bottom:4px">{e(uitleg)}</div>')
    tabel = [f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
             f'style="border-collapse:collapse">']
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
        tabel.append(f'<tr><td rowspan="{rijen_span}" valign="middle" style="padding-right:8px;font-size:12px;'
                     f'white-space:nowrap">{e(naam)}</td>{"".join(boven)}<td rowspan="{rijen_span}" valign="middle" '
                     f'style="padding-left:8px;font-size:13px;font-weight:bold;white-space:nowrap">'
                     f"{e(laatste_tekst)}</td></tr>")
        if tweezijdig:
            tabel.append(f'<tr>{"".join(onder)}</tr>')
    # Onderaan de dagen: de laatste en om de 7 dagen terug.
    labels = [f'<td class="grijs" style="font-size:11px;color:{GRIJS};text-align:center;white-space:nowrap">'
              f'{e(_dagnaam(d)) if (n - 1 - i) % stap == 0 else ""}</td>' for i, d in enumerate(dagen)]
    tabel.append(f'<tr><td></td>{"".join(labels)}<td></td></tr></table>')
    uit.append(f'<div class="scroll" style="overflow-x:auto">{"".join(tabel)}</div>')
    return "".join(uit)


# --- Tabellen ---

def tabel(koppen, rijen, eerste_links=1, klein=False):
    """
    Tabel met zebra-strepen en rechts uitgelijnde cijfers. rijen: lijst dicts met tekst per kop, of lijsten in de
    volgorde van de koppen; een cel is een tekst of (tekst, kleur) om de waarde te kleuren.
    """
    grootte = "12px" if klein else "13px"
    stijl_kop = f"padding:6px 8px;border-bottom:2px solid {GROEN};text-align:{{}};font-size:{grootte}"
    kop_ = "".join(f'<th class="rand" style="{stijl_kop.format("left" if i < eerste_links else "right")}">{e(k)}</th>'
                   for i, k in enumerate(koppen))
    body = []
    for nr, rij in enumerate(rijen):
        cellen = [rij.get(k, "") for k in koppen] if isinstance(rij, dict) else rij
        zebra = f' class="zebra" bgcolor="{LICHT}" style="background:{LICHT}"' if nr % 2 else ""
        body.append(f"<tr{zebra}>" + "".join(
            f'<td style="padding:5px 8px;text-align:{"left" if i < eerste_links else "right"};'
            f'font-size:{grootte}' + (f";color:{w[1]};font-weight:bold" if isinstance(w, tuple) else "") + '">'
            f'{e(w[0] if isinstance(w, tuple) else w)}</td>' for i, w in enumerate(cellen)) + "</tr>")
    return (f'<div class="scroll" style="overflow-x:auto"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="border-collapse:collapse"><tr>{kop_}</tr>{"".join(body)}</table></div>')
