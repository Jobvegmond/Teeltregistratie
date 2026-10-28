"""
PATS-tellingen (integrations/pats.py) omzetten naar regels voor de database en per dag optellen voor de tijdlijn.
Alleen rekenwerk; pats_import.py haalt op en slaat op. Tests in tests/test_pats.py.

- Trap-Eye (camera boven een vangplaat): ± 3 foto's per week. Per foto de stand op de plaat ("stand") en het
  aantal nieuwe sinds de vorige foto ("nieuw"); bij de eerste foto van een opgevraagde periode kan "nieuw"
  ontbreken. Soms halve tellingen.
- PATS-C (insectensensor): per dag, van 12 uur 's middags tot 12 uur de volgende dag; alleen "nieuw".
"""
from datetime import date

# De insecten in de tijdlijn, in deze volgorde (klasse-id bij PATS → naam). Anomalies (63) en No size (64)
# zijn geen insecten en worden niet opgeslagen.
INSECTEN = {28: "Trips", 24: "Witte vlieg", 27: "Mineervlieg", 2: "Duponchelia", 1: "Turkse mot"}
GEEN_INSECT = {63, 64}
APPARAAT = {"trapeye": "Trap-Eye", "c": "PATS-C"}


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


def dagtotalen(tellingen):
    """
    Per insect (INSECTEN) en dag het totaal nieuw over alle apparaten van de tuin:
    [{klasse_id, insect, datum, totaal, apparaten, met_vangst}], op insect (volgorde INSECTEN) en datum.
    Alleen dagen met een telling (Trap-Eye: een foto; PATS-C: elke dag).
    """
    per = {}
    for t in tellingen:
        if t["klasse_id"] not in INSECTEN or t["nieuw"] is None:
            continue
        d = per.setdefault((t["klasse_id"], t["datum"]), {"totaal": 0.0, "apparaten": 0, "met_vangst": 0})
        d["totaal"] += t["nieuw"]
        d["apparaten"] += 1
        d["met_vangst"] += t["nieuw"] > 0
    volgorde = list(INSECTEN)
    return [{"klasse_id": k, "insect": INSECTEN[k], "datum": dag, **d}
            for (k, dag), d in sorted(per.items(), key=lambda x: (volgorde.index(x[0][0]), x[0][1]))]
