"""
Behandelingen uit het blad Overview van het teeltlogboek "Klimaatregistratie tuin N" (Excel): de historie
vóór Agro4all.

Per vak staan er een regel GBM (gewasbescherming) en een regel Bio (biologie, bodemleven, voeding) met per dag
korte codes (Te, Ri, B5, …). Afspraak van de teler: codes in aaneengesloten dagcellen (en meer codes in één cel)
horen bij één behandeling op de eerste dag van die reeks. Hoeveelheden staan er niet in.

De kop van het blad heeft per week een blok van zeven dagen dat op zondag begint (jaar, week en dagletter in
de eerste drie rijen); zie kolomdatums(). De codes en hun middel staan in CODES; Fg (Florgib) en bekende
tikfouten worden overgeslagen. Alleen rekenwerk; tests in tests/test_klimaatregistratie.py.
"""
from datetime import date, timedelta

# Code → (middel, soort). Soort zoals bij Agro4all (logic/agro4all.soort): toegelaten middelen =
# gewasbescherming, biostimulanten/natuurlijke vijanden/bijvoer = biologie, meststoffen = voeding.
CODES = {
    "Te": ("Teppeki", "gewasbescherming"), "Pe": ("Pediment", "gewasbescherming"),
    "Ba": ("Batavia", "gewasbescherming"), "Ga": ("Gazelle", "gewasbescherming"),
    "Cl": ("Closer", "gewasbescherming"), "Si": ("Sivanto", "gewasbescherming"),
    "Sp": ("Spyro", "gewasbescherming"), "Ru": ("Runner", "gewasbescherming"),
    "Xe": ("XenTari", "gewasbescherming"), "No": ("Nocturn", "gewasbescherming"),
    "Pr": ("Proclaim", "gewasbescherming"), "Ve": ("Vectine", "gewasbescherming"),
    "Vec": ("Vectine", "gewasbescherming"), "Lu": ("Luna Privilege", "gewasbescherming"),
    "Ri": ("Rizolex", "gewasbescherming"), "Ra": ("Ranman", "gewasbescherming"),
    "Se": ("Serenade", "gewasbescherming"), "As": ("Asperello", "gewasbescherming"),
    "Sc": ("SilicaPower", "biologie"), "B5": ("Natrubac 08", "biologie"),
    "Rs": ("Root & Shoot", "biologie"), "RS": ("Root & Shoot", "biologie"),
    "M": ("MONcontrol", "biologie"), "P": ("Power Food", "biologie"), "D6": ("D-6 Force", "biologie"),
    "Xt": ("X-Tend", "voeding"), "Co": ("ConSecta", "voeding"),
    "Mn": ("Mangaan (INNO-Mn)", "voeding"), "Ijz": ("IJzer (Innofer)", "voeding"),
    "Yz": ("IJzer (Innofer)", "voeding"), "IM": ("IJzer en mangaan", "voeding"),
    "Im": ("IJzer en mangaan", "voeding"),
}
OVERSLAAN = {"Fg", "Fl", "La", "Ja"}       # Florgib staat al in de app; La en Ja zijn tikfouten
REGELS = ("GBM", "Bio")


def kolomdatums(jaren, weken, dagen):
    """{kolomindex: datum} uit de drie kopregels (jaar, weeknummer, dagletter; blok begint op zondag)."""
    uit, jaar, vorige_week, positie, blokstart = {}, None, None, 0, None
    for i in range(len(dagen)):
        if i < len(weken) and isinstance(weken[i], (int, float)) and dagen[i] in ("Z", "zo"):
            week = int(weken[i])
            kop_jaar = jaren[i] if i < len(jaren) and isinstance(jaren[i], (int, float)) else None
            if jaar is None:
                jaar = int(kop_jaar) if kop_jaar else None
            elif vorige_week is not None and week < vorige_week:
                jaar += 1
            elif kop_jaar and int(kop_jaar) > jaar:
                jaar = int(kop_jaar)
            vorige_week, positie = week, 0
            try:
                blokstart = date.fromisocalendar(jaar, week, 1) - timedelta(days=1) if jaar else None
            except ValueError:
                blokstart = None
        elif blokstart is not None:
            positie += 1
        if blokstart is not None and dagen[i]:
            uit[i] = blokstart + timedelta(days=positie)
    return uit


def _codes(waarde):
    return [c for c in str(waarde).split() if c] if isinstance(waarde, str) else []


def behandelingen(rijen, tot=None):
    """
    [(vak, datum, regel, [codes])] uit de rijen van het blad Overview (iterator van tuples, kop inbegrepen):
    per vak per regel (GBM/Bio) een behandeling per reeks aaneengesloten dagen met codes, op de eerste dag.
    `tot`: alleen behandelingen vóór die datum.
    """
    rijen = iter(rijen)
    jaren, weken, dagen = next(rijen), next(rijen), next(rijen)
    next(rijen)
    datums = kolomdatums(jaren, weken, dagen)
    kolommen = sorted(datums)
    uit, vak = [], None
    for rij in rijen:
        if rij and rij[0] is not None and isinstance(rij[0], (int, float)):
            vak = int(rij[0])
        if vak is None or len(rij) < 2 or rij[1] not in REGELS:
            continue
        reeks_start, reeks_codes, laatste = None, [], None
        for i in kolommen:
            codes = _codes(rij[i]) if i < len(rij) else []
            if not codes:
                continue
            dag = datums[i]
            if reeks_start is not None and dag - laatste == timedelta(days=1):
                reeks_codes += [c for c in codes if c not in reeks_codes]
            else:
                if reeks_start is not None:
                    uit.append((vak, reeks_start, rij[1], reeks_codes))
                reeks_start, reeks_codes = dag, list(codes)
            laatste = dag
        if reeks_start is not None:
            uit.append((vak, reeks_start, rij[1], reeks_codes))
    if tot is not None:
        uit = [b for b in uit if b[1] < tot]
    return uit


def regels(behandelingen_, tuin_nummer, bron):
    """
    (middelen, regels, onbekend) voor database.vervang_behandelingen: per behandeling per middel een regel
    (zonder hoeveelheid). onbekend: {code: aantal} voor codes die niet in CODES staan (die komen er als
    "code X" in, soort biologie bij de Bio-regel, anders gewasbescherming).
    """
    middelen, uit, onbekend = {}, [], {}
    for vak, dag, regel, codes in behandelingen_:
        gezien = set()
        for code in codes:
            if code in OVERSLAAN:
                continue
            naam, soort = CODES.get(code, (None, None))
            if naam is None:
                onbekend[code] = onbekend.get(code, 0) + 1
                naam, soort = f"code {code}", "biologie" if regel == "Bio" else "gewasbescherming"
            if naam in gezien:
                continue
            gezien.add(naam)
            middelen.setdefault(naam, {"code": naam, "naam": naam, "type": soort, "eenheid": None})
            uit.append({"tuin_nummer": tuin_nummer, "vaknummer": vak, "datum": dag, "middel_code": naam,
                        "dosering": None, "eenheid": None, "methode": None,
                        "opmerking": f"klimaatregistratie ({regel}: {' '.join(codes)})",
                        "extern_id": f"{bron}:{vak}:{dag.isoformat()}:{regel}:{naam}",
                        "registratie": f"{bron}:{dag.isoformat()}:{regel}:{' '.join(codes)}",
                        "doel": None, "mix": None, "aantal_vakken": None})
    return list(middelen.values()), uit, onbekend
