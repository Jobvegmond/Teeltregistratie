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

# --- AFDELINGEN ---
# Volgorde waarin de afdelingen overal getoond worden (teeltvolgorde), per
# tuinnummer. Een afdeling die hier niet staat komt er achteraan.
AFDELING_VOLGORDE = {
    1: (1, 2, 3, 4),
    3: (1, 3, 4, 2),
}

# --- NU: STATUS PER VAK ---
LENGTE_ORANJE_PCT = 5       # afwijking buiten ±5 % → oranje
LENGTE_ROOD_PCT = 10        # meer dan 10 % achter → rood (meer dan 10 % voor blijft oranje)
OOGST_ROOD_DAGEN = 5        # prognose-oogst meer dan 5 dagen na plan → rood
MIN_REFERENTIES = 3         # minder referentieteelten → grijs
REF_WEEKVENSTER = 2         # plantweek ±2 (eigen tuin, daarna beide tuinen)
REF_WEEKVENSTER_BREED = 4   # laatste stap van de ladder: ±4 in de eigen tuin ("≈")
MAX_PROGNOSE_DAGEN = 21     # prognose wijkt nooit meer dan 3 weken af van plan

# --- NU: MELDINGEN ---
KLIMAAT_TEMP_MARGE = 1.0    # °C boven (of onder) de ideale etmaaltemperatuur
KLIMAAT_VENSTER_DAGEN = 7   # kijk naar de laatste 7 dagen met klimaatdata
KLIMAAT_MIN_DAGEN = 4       # melding bij minstens 4 van die dagen buiten de marge
WATER_DROOG_DAGEN = 3       # melding bij zoveel dagen zonder gift (alleen vóór de Florgib)
STEK_RECENT_DAGEN = 21      # stekmeldingen alleen voor teelten die korter staan
STEK_GOED = {"Goed"}        # wortel/plantmaat/uniformiteit anders → melding
STEK_CIJFER_GRENS = 6       # stekcijfer ≤ 6 → melding
MAX_AANDACHTSPUNTEN = 8

# --- NU: STOOKADVIES (correctie c op de lichtlijn) ---
C_GRENZEN = (-2.0, 3.0)         # c niet verder dan dit; daarbuiten: prognose op de grens
OP_KOERS_MARGE = 0.2            # |c| kleiner dan dit: "op koers"
MELDING_C_DREMPEL = 0.3         # meldingen alleen bij |c| vanaf dit
MELDING_GRENS_MARGE_DAGEN = 2   # c op de grens: geen melding als de oogst dan hooguit zoveel dagen van plan ligt
FLORGIB_ACHTERSTAND_DAGEN = 3   # melding als de verwachte Florgib zoveel dagen voorbij is
AFWIJKING_VENSTER_DAGEN = 14    # "huidige stooklijn" = gemiddelde afwijking van de afdeling over zoveel dagen
