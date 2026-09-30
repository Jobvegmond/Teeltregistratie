"""
Watergift per vak en EC/pH per watersysteem: koppelen en samenvatten voor de
pagina Watergift. Alleen rekenwerk; tests in tests/test_watergift.py.
"""
from datetime import date, datetime, timedelta


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


def periode(eind_maandag, weken):
    """(van, tot): `weken` hele ISO-weken (ma–zo) t/m de week die op `eind_maandag` begint."""
    return eind_maandag - timedelta(weeks=weken - 1), eind_maandag + timedelta(days=6)


def dagen(van, tot):
    return [van + timedelta(days=i) for i in range((tot - van).days + 1)]


def teelt_op_dag(teelten_vak, dag, vandaag):
    """
    De teelt van een vak op een dag, of None (vak leeg). Een teelt loopt van
    de plantdag t/m de oogstdatum, of t/m vandaag als hij nog loopt.
    teelten_vak: dicts met start, florgib, oogst (dates of None), eerste_emmer.
    """
    for t in teelten_vak:
        eind = t["oogst"] or vandaag
        if t["start"] and t["start"] <= dag <= eind:
            return t
    return None


def markering(teelt, dag):
    """Wat er die dag in de teelt gebeurt: {"plant", "florgib", "oogst"} (deelverzameling) of None als het vak leeg is."""
    if teelt is None:
        return None
    uit = set()
    if dag == teelt["start"]:
        uit.add("plant")
    if teelt["florgib"] and dag == teelt["florgib"]:
        uit.add("florgib")
    begin_oogst = teelt.get("eerste_emmer") or teelt["oogst"]
    if begin_oogst and begin_oogst <= dag <= (teelt["oogst"] or dag):
        uit.add("oogst")
    return uit


def lopende_teelt(teelten_vak, vandaag):
    """De teelt die nu in het vak staat (gestart, nog niet geoogst), of None."""
    lopend = [t for t in teelten_vak if t["start"] and t["start"] <= vandaag and not t["oogst"]]
    return max(lopend, key=lambda t: t["start"]) if lopend else None


def totaal_sinds_planten(gift_vak, start, tot):
    """Totale watergift (l/m²) van een vak van `start` t/m `tot`; gift_vak = {dag: liter}."""
    return sum(liter or 0.0 for dag, liter in gift_vak.items() if start <= dag <= tot)


def band_status(waarde, band):
    """"laag" / "hoog" als de waarde buiten de band (min, max) valt, anders None."""
    if waarde is None or band is None:
        return None
    if waarde < band[0]:
        return "laag"
    if waarde > band[1]:
        return "hoog"
    return None


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


def toon_behandelingen(behandelingen):
    """De subregel met behandelingen verschijnt pas als er behandelingen zijn; zolang de tabel leeg is niet."""
    return bool(behandelingen)


def behandelingen_per_vak_dag(behandelingen):
    """{(vak, dag): [(code, type), ...]} uit behandelingregels (dicts met vaknummer, datum, code, type)."""
    uit = {}
    for b in behandelingen:
        uit.setdefault((int(b["vaknummer"]), als_datum(b["datum"])), []).append((b["code"], b["type"]))
    return uit
