"""
Instelbare waarden van de teeltregistratie, op één plek. Pas hier aan; de
rekenmodules in logic/ en het scherm lezen ze hieruit.
"""

# --- LICHTLIJN (stookregel) ---
# Ideale etmaaltemperatuur bij de lichtsom BINNEN van die dag (J/cm² per dag):
# T_ideaal = LICHTLIJN_BASIS + LICHTLIJN_FACTOR × lichtsom. Eén plek, gebruikt
# door logic/lichtlijn.py (en via daar door de app).
LICHTLIJN_BASIS = 11.7
LICHTLIJN_FACTOR = 0.0072

# --- TEELTSTRATEGIE (streefwaarden; pagina Tuin, uitleg bij de kengetallen) ---
# Uit de bedrijfsomschrijving: altijd een positieve DIF van minstens 2 °C (dag warmer dan nacht), de
# stooklijn nooit boven 15,5 °C, EC van de gift 1,0–2,0 en pH het liefst 5,0–5,5 (tuin 3 heeft geen
# pH-regeling).
DIF_MIN = 2.0
STOOK_MAX = 15.5
EC_BEREIK = (1.0, 2.0)
PH_BEREIK = (5.0, 5.5)

# --- RAPPORT "TEELT AFGEROND" (teelt_rapport.py) ---
# Mail zodra het laatste vak van een plantweek geoogst is. Alleen teelten die op of na RAPPORT_VANAF zijn afgerond
# (oudere niet alsnog). Het adres kan in de omgeving overschreven worden (RAPPORT_AAN).
from datetime import date as _date
RAPPORT_AAN = "info@tanacetum.nl"
RAPPORT_VANAF = _date(2026, 10, 20)
APP_URL = "https://vemteelt.onrender.com"

# --- ENERGIE ---
# Calorische waarde van aardgas (bovenwaarde Groningen-gas, geen rendementscorrectie),
# om m³ gas om te rekenen naar MJ.
GAS_CALORISCHE_WAARDE_MJ_PER_M3 = 31.65

# --- AFDELINGEN ---
# Volgorde waarin de afdelingen overal getoond worden (teeltvolgorde), per
# tuinnummer. Een afdeling die hier niet staat komt er achteraan.
AFDELING_VOLGORDE = {
    1: (1, 2, 3, 4),
    3: (1, 3, 4, 2),
}

# --- TEELTOVERZICHT: STATUS PER VAK (vakkenmatrix) ---
LENGTE_ORANJE_PCT = 5       # afwijking buiten ±5 % → oranje
LENGTE_ROOD_PCT = 10        # meer dan 10 % achter → rood (meer dan 10 % voor blijft oranje)
OOGST_ROOD_DAGEN = 5        # prognose-oogst meer dan 5 dagen na plan → rood
MIN_REFERENTIES = 3         # minder referentieteelten → grijs
REF_WEEKVENSTER = 2         # plantweek ±2 (eigen tuin, daarna beide tuinen)
REF_WEEKVENSTER_BREED = 4   # laatste stap van de ladder: ±4 in de eigen tuin ("≈")
MAX_PROGNOSE_DAGEN = 21     # prognose wijkt nooit meer dan 3 weken af van plan

# --- TEELTOVERZICHT: STOOKADVIES (correctie c op de lichtlijn) ---
C_GRENZEN = (-2.0, 3.0)         # c niet verder dan dit; daarbuiten: prognose op de grens
OP_KOERS_MARGE = 0.2            # |c| kleiner dan dit: "op koers"
FLORGIB_ACHTERSTAND_DAGEN = 3   # gestippelde rand als de verwachte Florgib zoveel dagen voorbij is
AFWIJKING_VENSTER_DAGEN = 14    # "huidige stooklijn" = gemiddelde afwijking van de afdeling over zoveel dagen

# --- OPMERKINGEN PER VAK ---
OPMERKING_CATEGORIEEN = ("Groei", "Ziekte/plagen", "Water", "Klimaat", "Overig")

# --- WATERGIFT ---
# Welk Priva-watersysteem het water (en dus de EC/pH) levert, per tuin:
# {tuinnummer: {watersysteem: vaknummers}}; None = alle vakken van die tuin.
# Tuin 1 heeft ook een watersysteem 2, maar dat wordt niet gebruikt.
WATERSYSTEMEN = {1: {1: None}, 3: {1: None}}

# --- PRIVA-BESTANDEN OP DE NAS ---
# Per tuin waar de Priva-bestanden staan (in de share Priva, in de container /priva): de regelaar (staat ook
# in laatste.json en water-actueel.json en wordt gecontroleerd), de map met de minuutbestanden (live) en die
# met de dagbestanden en de uurhistorie (historie), en welke pulsmeter wat meet. Tuin 1 krijgt zijn warmte van
# de warmtewisselaar, niet uit een pulsmeter (pulsmeter 2 staat daar op 0): de warmte komt daar uit het
# gerealiseerde vermogen van de warmtewisselaar (warmte_vermogen, kW, scherm M340.0) maal de tijd.
PRIVA_BESTANDEN = {
    3: {"pcu": "VP9508", "live": "bron live", "historie": "bron historie", "meters": {1: "gas", 2: "warmte"}},
    1: {"pcu": "Matricaria25", "live": "bron historie/Tuin 1/live", "historie": "bron historie/Tuin 1/historie",
        "meters": {1: "gas"}, "warmte_vermogen": "M340.0N1R11.1V1"},
}

# --- VERSIE ---
# Staat rechtsboven in de app. Ophogen bij elke wijziging op main (zie CHANGELOG.md):
# derde getal bij een correctie, tweede bij iets nieuws, eerste bij een grote omzetting.
APP_VERSIE = "2.20.1"
