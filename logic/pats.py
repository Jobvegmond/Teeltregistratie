"""
PATS-tellingen (integrations/pats.py) omzetten naar regels voor de database en per dag optellen voor de tijdlijn.
Alleen rekenwerk; pats_import.py haalt op en slaat op. Tests in tests/test_pats.py.

- Trap-Eye (camera boven een vangplaat): ± 3 foto's per week. Per foto de stand op de plaat ("stand") en het
  aantal nieuwe sinds de vorige foto ("nieuw"); bij de eerste foto van een opgevraagde periode kan "nieuw"
  ontbreken. Soms halve tellingen.
- PATS-C (insectensensor): per dag, van 12 uur 's middags tot 12 uur de volgende dag; alleen "nieuw".
"""
from datetime import date

# De namen van de insecten (klasse-id bij PATS → naam). Alles wordt opgeslagen; Anomalies (63) en No size (64)
# zijn geen insecten en worden niet opgeslagen.
INSECTEN = {28: "Trips", 24: "Witte vlieg", 27: "Mineervlieg", 2: "Duponchelia", 1: "Turkse mot"}
# Wat de tijdlijn toont, in deze volgorde: trips (Trap-Eye) en turkse mot (PATS-C); de rest vindt de teler
# minder interessant (oktober 2026).
GETOOND = (28, 1)
GEEN_INSECT = {63, 64}
APPARAAT = {"trapeye": "Trap-Eye", "c": "PATS-C"}
# De insecten van de vangplaten (Trap-Eye) in de regel "plaat" onder elk vak, met hun letter (bij één insect
# alleen het getal).
PLAAT_INSECTEN = {28: "T"}


def als_datum(tekst):
    """'20260101' → date."""
    return date(int(tekst[:4]), int(tekst[4:6]), int(tekst[6:8]))


def _getal(waarde):
    return None if waarde is None else float(waarde)


def regels(antwoord, klassen, tuin_id, section_id):
    """
    De tellingen (antwoord van /api/v2/counts) als regels per apparaat, dag en insect:
    {tuin_id, section_id, apparaat, rij, paal, datum, klasse_id, klasse, nieuw, stand}.
    klassen: {klasse_id: naam} (uit de section).
    """
    uit = {}

    def regel(apparaat, a, datum, klasse_id):
        sleutel = (apparaat, a.get("row_id"), a.get("post_id"), datum, klasse_id)
        if sleutel not in uit:
            uit[sleutel] = {"tuin_id": tuin_id, "section_id": section_id, "apparaat": apparaat,
                            "rij": a.get("row_id"), "paal": a.get("post_id"), "datum": datum, "klasse_id": klasse_id,
                            "klasse": klassen.get(klasse_id) or str(klasse_id), "nieuw": None, "stand": None}
        return uit[sleutel]

    def waarden(dag):
        for k, n in dag.items():
            if k not in ("date", "datetime") and int(k) not in GEEN_INSECT:
                yield int(k), _getal(n)

    for a in antwoord.get("trapeye") or []:
        for veld, reeks in (("stand", "absolute_count"), ("nieuw", "new_counts")):
            for dag in a.get(reeks) or []:
                for klasse_id, n in waarden(dag):
                    regel("trapeye", a, als_datum(dag["date"]), klasse_id)[veld] = n
    for a in antwoord.get("c") or []:
        for dag in a.get("counts") or []:
            if "date" not in dag:           # alleen dagtellingen
                continue
            for klasse_id, n in waarden(dag):
                regel("c", a, als_datum(dag["date"]), klasse_id)["nieuw"] = n
    return sorted(uit.values(), key=lambda r: (r["apparaat"], r["rij"] or 0, r["paal"] or 0, r["datum"],
                                               r["klasse_id"]))


def vakken_van_rij(rij, verschuiving):
    """De vakken naast een Trap-Eye-rij: verschuiving (a, b) → (rij + a, rij + b); tuin 3: (−1, 0)."""
    return [rij + d for d in verschuiving]


def per_vak(tellingen, verschuiving, vakken):
    """
    De nieuwe vangst van de Trap-Eyes per vak en fotodag: een plaat telt voor beide buurvakken.
    [{vak, datum, nieuw: {klasse_id: n}, platen: [(rij, paal)]}], op vak en datum; alleen PLAAT_INSECTEN, alleen
    platen met een bekende "nieuw" en alleen vakken uit `vakken`.
    """
    per = {}
    for t in tellingen:
        if t["apparaat"] != "trapeye" or t["klasse_id"] not in PLAAT_INSECTEN or t["nieuw"] is None:
            continue
        for vak in vakken_van_rij(t["rij"], verschuiving):
            if vak not in vakken:
                continue
            d = per.setdefault((vak, t["datum"]), {"nieuw": {k: 0.0 for k in PLAAT_INSECTEN}, "platen": set()})
            d["nieuw"][t["klasse_id"]] += t["nieuw"]
            d["platen"].add((t["rij"], t["paal"]))
    return [{"vak": vak, "datum": dag, "nieuw": d["nieuw"], "platen": sorted(d["platen"])}
            for (vak, dag), d in sorted(per.items())]


def kort(nieuw):
    """{klasse_id: n} → "T3 M1" (alleen wat er gevangen is; bij één insect alleen "3"), of "0"."""
    def getal(n):
        return f"{n:g}".replace(".", ",")
    if len(PLAAT_INSECTEN) == 1:
        return getal(sum(nieuw.get(k) or 0 for k in PLAAT_INSECTEN))
    delen = [f"{letter}{getal(nieuw[k])}" for k, letter in PLAAT_INSECTEN.items() if nieuw.get(k)]
    return " ".join(delen) or "0"


def dagtotalen(tellingen):
    """
    Per getoond insect (GETOOND) en dag het totaal nieuw over alle apparaten van de tuin:
    [{klasse_id, insect, datum, totaal, apparaten, met_vangst}], op insect (volgorde GETOOND) en datum.
    Alleen dagen met een telling (Trap-Eye: een foto; PATS-C: elke dag).
    """
    per = {}
    for t in tellingen:
        if t["klasse_id"] not in GETOOND or t["nieuw"] is None:
            continue
        d = per.setdefault((t["klasse_id"], t["datum"]), {"totaal": 0.0, "apparaten": 0, "met_vangst": 0})
        d["totaal"] += t["nieuw"]
        d["apparaten"] += 1
        d["met_vangst"] += t["nieuw"] > 0
    volgorde = list(GETOOND)
    return [{"klasse_id": k, "insect": INSECTEN[k], "datum": dag, **d}
            for (k, dag), d in sorted(per.items(), key=lambda x: (volgorde.index(x[0][0]), x[0][1]))]
