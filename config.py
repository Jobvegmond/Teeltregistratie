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
