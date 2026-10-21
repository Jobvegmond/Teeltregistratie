"""
Watergift per vak en EC/pH per watersysteem: koppelen en samenvatten voor de
pagina Watergift. Alleen rekenwerk; tests in tests/test_watergift.py.
"""
from datetime import date, datetime, timedelta

from logic.weken import week_begin, weeknummer  # noqa: F401 (week_begin/weeknummer via wg.* in app.py)


def watersysteem_van_vak(watersystemen, tuin_nummer, vak):
    """Het watersysteem dat dit vak water geeft (config.WATERSYSTEMEN), of None."""
    for systeem, vakken in sorted(watersystemen.get(tuin_nummer, {}).items()):
        if vakken is None or vak in vakken:
            return systeem
    return None


def vakken_van_watersysteem(watersystemen, tuin_nummer, systeem, alle_vakken):
    """De vakken (laag naar hoog) die water krijgen van dit watersysteem; `alle_vakken` = de vakken van de tuin."""
    vakken = watersystemen.get(tuin_nummer, {}).get(systeem, ())
    if vakken is None:
        return sorted(alle_vakken)
    return sorted(v for v in vakken if v in set(alle_vakken))


# --- Pagina Watergift: matrix vak × dag ---


def als_datum(waarde):
    if waarde is None or waarde != waarde or waarde == "":
        return None
    if isinstance(waarde, datetime):
        return waarde.date()
    if isinstance(waarde, date):
        return waarde
    return datetime.strptime(str(waarde)[:10], "%Y-%m-%d").date()


def dagen(van, tot):
    return [van + timedelta(days=i) for i in range((tot - van).days + 1)]


def samenvatting(gift, vakken_afd, m2, bezet, van, tot):
    """
    Watergift van één groep vakken (bijv. een afdeling) over van..tot:
    {"gift_per_dag", "giftdagen", "laatste"}.
    - gift_per_dag: m²-gewogen gemiddelde l/m² per bezette vak-dag (een leeg vak telt niet mee);
    - giftdagen: dagen waarop minstens één vak water kreeg;
    - laatste: de laatste dag met gift in de periode.
    gift = {(vak, dag): liter}; m2 = {vak: m²}; bezet(vak, dag) → bool.
    """
    teller = noemer = 0.0
    giftdagen = set()
    for dag in dagen(van, tot):
        for vak in vakken_afd:
            liter = gift.get((vak, dag))
            if liter:
                giftdagen.add(dag)
            if bezet(vak, dag):
                opp = m2.get(vak) or 1.0
                teller += (liter or 0.0) * opp
                noemer += opp
    return {"gift_per_dag": teller / noemer if noemer else None, "giftdagen": len(giftdagen),
            "laatste": max(giftdagen) if giftdagen else None}


def gemiddelde(waarden):
    waarden = [w for w in waarden if w is not None]
    return sum(waarden) / len(waarden) if waarden else None


# Bij meer soorten op één dag krijgt het driehoekje op de tijdlijn de kleur van de eerste in deze volgorde.
BEHANDELING_VOLGORDE = ("gewasbescherming", "biologie", "voeding")
BEHANDELING_KLEUR = {"gewasbescherming": "#d64541", "biologie": "#2e9d5b", "voeding": "#8a6d3b"}


def behandelingen_per_vak_dag(behandelingen):
    """{(vak, dag): [behandelingregels]} uit dicts met (minstens) vaknummer, datum en type."""
    uit = {}
    for b in behandelingen:
        uit.setdefault((int(b["vaknummer"]), als_datum(b["datum"])), []).append(b)
    return uit


def hoofdsoort(regels):
    """De soort waarvan het driehoekje de kleur krijgt (gewasbescherming vóór biologie vóór voeding), of None."""
    soorten = {r.get("type") for r in regels}
    return next((s for s in BEHANDELING_VOLGORDE if s in soorten), None)


def behandeling_tekst(b):
    """Eén regel: "Rizolex vloeibaar 900 ml in 100 l (tegen Rhizoctonia soorten)"."""
    hoeveel = ""
    if b.get("dosering") is not None:
        dosering = f"{b['dosering']:g}".replace(".", ",")
        hoeveel = f" {dosering} {b.get('eenheid') or ''}".rstrip()
    mix = f" in {b['mix']}" if b.get("mix") else ""
    doel = f" (tegen {b['doel']})" if b.get("doel") else ""
    naam = b.get("naam") or b.get("middel") or "?"
    return f"{naam}{hoeveel}{mix}{doel}"
