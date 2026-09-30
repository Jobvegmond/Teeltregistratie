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


def periode(eind_zondag, weken):
    """(van, tot): `weken` hele weken (zo–za) t/m de week die op `eind_zondag` begint."""
    return eind_zondag - timedelta(weeks=weken - 1), eind_zondag + timedelta(days=6)


def dagen(van, tot):
    return [van + timedelta(days=i) for i in range((tot - van).days + 1)]


def teelt_op_dag(teelten_vak, dag, vandaag):
    """
    De teelt van een vak op een dag, of None (vak leeg). Een teelt loopt van de
    plantdag t/m de oogstdatum; nog niet geoogst: t/m de verwachte oogst
    (prognose, plan of concept), en een gestarte teelt minstens t/m vandaag.
    teelten_vak: dicts met start, florgib, oogst, verwacht_oogst, eerste_emmer.
    """
    # Echte teelten gaan voor: een concept dat over een gestarte teelt heen valt, telt daar niet.
    for t in sorted(teelten_vak, key=lambda t: bool(t.get("concept"))):
        if not t["start"]:
            continue
        if t["oogst"]:
            eind = t["oogst"]
        else:
            # Nog niet geoogst: t/m de verwachte oogst, en een gestarte teelt minstens t/m vandaag.
            eind = max([e for e in (t.get("verwacht_oogst"), vandaag if t["start"] <= vandaag else None) if e]
                       or [t["start"]])
        if t["start"] <= dag <= eind:
            return t
    return None


def markering(teelt, dag, vandaag=None):
    """
    Wat er die dag in de teelt gebeurt, als deelverzameling van {"plant",
    "florgib", "florgib_verwacht", "oogst", "oogst_verwacht"}, of None als het
    vak leeg is. florgib_verwacht: de dag waarop het teeltmodel de Florgib
    verwacht, zolang er nog geen Florgib geregistreerd is.
    - oogst: de laatste oogstdag (oogstdatum; nog niet afgerond: de laatste emmerdag);
    - oogst_verwacht: de verwachte oogstdag van een teelt die nog niet geoogst wordt.
    """
    if teelt is None:
        return None
    uit = set()
    if dag == teelt["start"]:
        uit.add("plant")
    if teelt["florgib"] and dag == teelt["florgib"]:
        uit.add("florgib")
    elif not teelt["florgib"] and teelt.get("florgib_verwacht") and dag == teelt["florgib_verwacht"]:
        uit.add("florgib_verwacht")
    # Alleen de laatste oogstdag: de oogstdatum, of zolang het vak niet is afgerond de laatste emmerdag.
    if dag == (teelt["oogst"] or teelt.get("laatste_emmer")):
        uit.add("oogst")
    elif not teelt["oogst"] and not teelt.get("eerste_emmer") and dag == teelt.get("verwacht_oogst"):
        uit.add("oogst_verwacht")
    return uit


def rondes(teelten, startvak, aantal_kleuren=3):
    """
    Deelt de teelten van een tuin in teeltrondes in: een ronde begint bij elke
    planting van het startvak (tuin 3: vak 2) en loopt daarna de vakken door.
    Elke teelt krijgt:
    - "ronde": het rondenummer (0 = vóór de eerste bekende planting van het startvak);
    - "kleur": ronde % aantal_kleuren, één kleur per ronde;
    - "tint": 0/1, om en om per teelt (plantweek) binnen de ronde: licht/donker.
    Valt een teelt op dezelfde dag als een planting van het startvak, dan horen
    de vakken vlak na het startvak bij de nieuwe ronde en de laatste vakken bij
    de oude. teelten = {vak: [teelt]}.
    """
    def week(t):
        return t["start"].isocalendar()[:2]

    starts = sorted(t["start"] for t in teelten.get(startvak, []) if t["start"])
    helft = max(teelten or [startvak]) // 2
    per_ronde = {}
    for vak, lijst in teelten.items():
        for t in lijst:
            if not t["start"]:
                continue
            ronde = sum(1 for d in starts if d < t["start"])
            if t["start"] in starts and (vak == startvak or 0 < vak - startvak <= helft):
                ronde += 1
            t["ronde"] = ronde
            per_ronde.setdefault(ronde, set()).add(week(t))
    volgorde = {r: {w: i for i, w in enumerate(sorted(weken))} for r, weken in per_ronde.items()}
    for lijst in teelten.values():
        for t in lijst:
            if t["start"]:
                t["kleur"] = t["ronde"] % aantal_kleuren
                t["tint"] = volgorde[t["ronde"]][week(t)] % 2
    return teelten


def laatste_eind(teelten, met_concepten=False):
    """
    De verste dag waarop een teelt nog loopt (oogst of verwachte oogst), of None.
    Standaard alleen echte teelten (gestart of bevestigd): de concept-planning
    loopt vaak een jaar vooruit.
    """
    einden = [t["oogst"] or t.get("verwacht_oogst") for lijst in teelten.values() for t in lijst
              if met_concepten or not t.get("concept")]
    einden = [e for e in einden if e]
    return max(einden) if einden else None


def lopende_teelt(teelten_vak, vandaag):
    """De teelt die nu in het vak staat (gestart, nog niet geoogst, geen concept), of None."""
    lopend = [t for t in teelten_vak if t["start"] and t["start"] <= vandaag and not t["oogst"]
              and not t.get("concept")]
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
