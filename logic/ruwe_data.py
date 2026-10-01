"""
Ruwe data (Meer › Ruwe data): de onderliggende tabellen om iets op te zoeken,
alleen lezen. Per tabel een vaste SELECT met de tuin, de datum (voor de
periode) en het vak, zodat de pagina dezelfde filters kan gebruiken als de rest
van de app. Gebruikers, instellingen en het logboek staan hier bewust niet in
(wachtwoorden; het logboek heeft een eigen tabblad). Tests in
tests/test_ruwe_data.py.
"""
from dataclasses import dataclass

# Vak en afdeling via teeltvakken, voor de tabellen die alleen een teelt_id hebben.
_VAK = "JOIN teelten t ON t.id = {a}.teelt_id JOIN teeltvakken v ON v.id = t.teeltvak_id"


@dataclass(frozen=True)
class Tabel:
    naam: str            # in de keuzelijst
    select: str          # SELECT … FROM … (JOIN …), zonder WHERE
    tuin: str            # kolom met de tuin_id
    datum: str = None    # kolom met de datum (tekst 'jjjj-mm-dd' of date), None = geen periodefilter
    vak: str = None      # kolom met het vaknummer, None = geen vakfilter
    volgorde: str = ""   # ORDER BY (laag → hoog)
    uitleg: str = ""


TABELLEN = [
    Tabel("Vakken (teelten)",
          "SELECT t.code, v.vaknummer AS vak, v.afdeling, t.ras, t.datum_teelt_start AS plantdatum, "
          "t.aantal_planten AS planten, t.datum_half AS florgib, t.lengte_half AS lengte_florgib, "
          "t.florgib_gram, t.datum_oogst AS oogstdatum, t.lengte_eind AS oogstlengte, t.oogstgewicht, "
          "t.rijpheid, t.uitval_pct, t.id AS teelt_id FROM teelten t JOIN teeltvakken v ON v.id = t.teeltvak_id",
          "v.tuin_id", "t.datum_teelt_start", "v.vaknummer", "t.datum_teelt_start, v.vaknummer",
          "Elk vak (één teeltronde) zoals vastgelegd; periode = plantdatum."),
    Tabel("Emmers (oogst)",
          "SELECT o.datum, v.vaknummer AS vak, v.afdeling, t.code, o.aantal_emmers AS emmers, "
          "o.aantal_emmers * 100 AS stelen, o.id FROM oogstregistraties o " + _VAK.format(a="o"),
          "v.tuin_id", "o.datum", "v.vaknummer", "o.datum, v.vaknummer",
          "Elk oogstmoment; stelen = emmers × 100."),
    Tabel("Klimaat per dag",
          "SELECT datum, afdeling, gem_temperatuur AS etmaal_temp, gem_temperatuur_dag AS temp_dag, "
          "gem_temperatuur_nacht AS temp_nacht, gem_rv AS rv, gem_rv_dag AS rv_dag, gem_rv_nacht AS rv_nacht, "
          "stralingssom_dag AS lichtsom FROM klimaatdata_dag",
          "tuin_id", "datum", None, "datum, afdeling", "Daggemiddelden per afdeling (Priva)."),
    Tabel("Watergift per dag",
          "SELECT datum, vaknummer AS vak, liter_per_m2, beurten, ec, ph, bron FROM watergift_dag",
          "tuin_id", "datum", "vaknummer", "datum, vaknummer", "Gift per vak per dag; EC/pH gewogen naar de liters."),
    Tabel("Gietbeurten",
          "SELECT datum, start, eind, vaknummer AS vak, liter_per_m2, ec, ph, flow, bron FROM watergift_beurt",
          "tuin_id", "datum", "vaknummer", "start, vaknummer", "Elke gietbeurt (sinds 2.4.1), tijden in Nederlandse tijd."),
    Tabel("EC/pH per dag",
          "SELECT datum, watersysteem, ec_aanvoer, ec_gift, ph_gift, ec_gem, ec_min, ec_max, ph_gem, ph_min, "
          "ph_max, ec_doel, ph_doel, recept, metingen, bron FROM water_kwaliteit_dag",
          "tuin_id", "datum", None, "datum, watersysteem", "Per watersysteem per dag (sinds 27-09-26)."),
    Tabel("Warmte per dag",
          "SELECT datum, warmte_mj_totaal, warmte_mj_per_m2 FROM energiedata_dag",
          "tuin_id", "datum", None, "datum", "Uit de energie-export van Priva."),
    Tabel("Gas per dag",
          "SELECT datum, gas_m3_totaal, gas_m3_per_m2, gas_mj_totaal, gas_mj_per_m2 FROM gasdata_dag",
          "tuin_id", "datum", None, "datum", "Uit de energie-export van Priva."),
    Tabel("Stek",
          "SELECT t.datum_teelt_start AS plantdatum, v.vaknummer AS vak, t.code, s.ras, s.bakjes, s.wortel, "
          "s.plantmaat, s.uniformiteit, s.beoordeling, s.opmerking FROM stekbeoordelingen s " + _VAK.format(a="s"),
          "v.tuin_id", "t.datum_teelt_start", "v.vaknummer", "t.datum_teelt_start, v.vaknummer",
          "Stekbeoordeling per vak; periode = plantdatum."),
    Tabel("Opmerkingen",
          "SELECT o.datum, v.vaknummer AS vak, t.code, o.categorie, o.tekst, o.gebruiker, o.aangemaakt_op, "
          "o.gewijzigd_op FROM opmerkingen o " + _VAK.format(a="o"),
          "v.tuin_id", "o.datum", "v.vaknummer", "o.datum, v.vaknummer", "Alle opmerkingen bij vakken."),
    Tabel("Concept-planning",
          "SELECT verwachte_startdatum AS startdatum, vaknummer AS vak, verwachte_duur_weken AS duur_weken, "
          "verwachte_oogstdatum AS oogstdatum, notitie, aangemaakt_op FROM teeltplanning",
          "tuin_id", "verwachte_startdatum", "vaknummer", "verwachte_startdatum, vaknummer",
          "Concepten die nog niet gestart zijn."),
    Tabel("Jaarplanning (weekdoelen)",
          "SELECT week_start, aantal_vakken, vak1_planten FROM planning_weekdoel",
          "tuin_id", "week_start", None, "week_start", "Aantal te poten vakken per week (Planning)."),
    Tabel("Prognoselogboek",
          "SELECT datum, vaknummer AS vak, afdeling, code, leeftijd_d, fase, gedaan, plan_oogst, prognose_oogst, "
          "correctie_c, c_begrensd, stooklijn, stooklijn_bron, modelversie FROM prognose_log",
          "tuin_id", "datum", "vaknummer", "datum, vaknummer", "De dagelijkse prognose per lopend vak."),
    Tabel("Teelthistorie",
          "SELECT startdatum, vaknummer AS vak, afdeling, code, plantjaar, plantweek, start_precisie, oogstdatum, "
          "oogst_precisie, teeltduur_dagen, florgib_datum, florgib_bron, lengte_eind, oogstgewicht, bron "
          "FROM teelt_historie",
          "tuin_id", "startdatum", "vaknummer", "startdatum, vaknummer",
          "Historie uit de klimaatregistratie (Excel) en afgeronde vakken; leerdata van het teeltmodel."),
    Tabel("Teelthistorie per week",
          "SELECT th.startdatum, th.vaknummer AS vak, th.code, w.isojaar, w.isoweek, w.etmaal_temp, "
          "w.lichtsom_binnen, w.bron FROM teelt_historie_week w JOIN teelt_historie th ON th.id = w.historie_id",
          "th.tuin_id", "th.startdatum", "th.vaknummer", "th.startdatum, th.vaknummer, w.isojaar, w.isoweek",
          "Klimaat per teeltweek van de historie; periode = plantdatum."),
    Tabel("Vakgegevens",
          "SELECT vaknummer AS vak, afdeling, naam, oppervlakte_m2, stelen_bij_60 FROM teeltvakken",
          "tuin_id", None, "vaknummer", "vaknummer", "Oppervlakte en afdeling per vak."),
]


def tabel(naam):
    return next(t for t in TABELLEN if t.naam == naam)


def query(t, tuin_id, van=None, tot=None, vakken=()):
    """
    (sql, params) voor tabel `t` in één tuin, optioneel binnen [van, tot] (beide
    inclusief, op de datumkolom) en voor bepaalde vakken. De SQL bestaat alleen
    uit de vaste stukken uit TABELLEN; alles van de gebruiker gaat als parameter.
    """
    waar, params = [f"{t.tuin} = %s"], [tuin_id]
    if t.datum and van is not None:
        waar.append(f"SUBSTRING(CAST({t.datum} AS TEXT), 1, 10) BETWEEN %s AND %s")
        params += [str(van), str(tot)]
    if t.vak and vakken:
        waar.append(f"{t.vak} IN ({', '.join(['%s'] * len(vakken))})")
        params += [int(v) for v in vakken]
    sql = f"{t.select} WHERE {' AND '.join(waar)}" + (f" ORDER BY {t.volgorde}" if t.volgorde else "")
    return sql, params


def zoek(rijen, tekst):
    """De rijen (dicts) waarin `tekst` ergens voorkomt (hoofdletterongevoelig)."""
    tekst = (tekst or "").strip().lower()
    if not tekst:
        return list(rijen)
    return [r for r in rijen if any(tekst in str(w).lower() for w in r.values() if w is not None)]
