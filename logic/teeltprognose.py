"""
Prognose en stookadvies per lopende teelt, op basis van het teeltmodel.

- Leerdata: teelt_historie (+ weekwaarden) aangevuld met teelten die in de app
  zijn afgerond en nog niet in de historie staan. Het model leert zo mee met
  elke nieuwe oogst; er staan hier geen vaste teeltgetallen.
- Model: regressie op licht en afwijking van de lichtlijn, met tuincorrectie
  (logic/teeltmodel.py). Licht en temperatuur lopen over de hele teelt.
- Florgib: indicator van hoe ver de teelt is. Op de dag van de registratie
  wordt de voortgang gelijkgezet op het mediane deel waarop teelten gespoten
  worden (uit de historie); zonder registratie volgt daaruit de verwachte
  Florgib-datum.
- Toekomst: licht = meerjarig gemiddelde per kalenderweek; temperatuur =
  lichtlijn + de gemiddelde afwijking van de afdeling (laatste 14 dagen), of
  lichtlijn + c voor het advies.
- c: de constante afwijking van de lichtlijn waarmee de teelt precies op de
  plandatum oogstrijp is (bisectie, binnen config.C_GRENZEN).

Alles werkt op pandas-DataFrames en numpy; geen database, geen Streamlit.
"""
from datetime import date, datetime, timedelta

import numpy as np

from config import AFWIJKING_VENSTER_DAGEN, C_GRENZEN, OP_KOERS_MARGE
from logic.lichtlijn import t_ideaal
from logic.teeltmodel import (LineairModel, MetTuinfactor, benodigde_correctie, duur_uit_snelheid,
                              florgib_fractie, ontwikkeling, voor_tuin)

DUUR_GRENZEN = (28, 140)
TOEKOMST_DAGEN = 160


def _datum(waarde):
    if waarde is None or waarde != waarde:
        return None
    if isinstance(waarde, date):
        return waarde
    return datetime.strptime(str(waarde)[:10], "%Y-%m-%d").date()


def _getal(waarde):
    if waarde is None:
        return None
    try:
        waarde = float(waarde)
    except (TypeError, ValueError):
        return None
    return None if waarde != waarde else waarde


def dagreeks(start, dagen, bron):
    """(T, L) als arrays voor `dagen` dagen vanaf start uit bron {datum: (T, L)}; None bij een gat aan het begin."""
    T, L, vorige = [], [], None
    for i in range(dagen):
        x = bron.get(start + timedelta(days=i)) or vorige
        if x is None:
            return None
        vorige = x
        T.append(x[0])
        L.append(x[1])
    return np.array(T, float), np.array(L, float)


def klimaat_per_afdeling(klimaat):
    """
    {(tuin_id, afdeling): {datum: (T, L)}} uit de klimaat-DataFrame van het
    scherm (tuin_id, afdeling, datum, temp_24h, lichtsom). Dagen zonder
    temperatuur of licht tellen niet.
    """
    uit = {}
    for r in klimaat.itertuples():
        T, L = _getal(r.temp_24h), _getal(r.lichtsom)
        if T is None or L is None:
            continue
        uit.setdefault((int(r.tuin_id), int(r.afdeling)), {})[_datum(r.datum)] = (T, L)
    return uit


def bouw_leerset(historie, historie_week, app_teelten, klimaat_afd, geschatte_oogst):
    """
    Afgeronde teelten als dicts (tuin, start, duur, T, L, florgib_dag, gewicht, lengte).
    `tuin` is de tuin_id: de tuincorrectie werkt per tuin_id.
    - historie / historie_week: zie database.get_teelthistorie_data().
    - app_teelten: de teelten-DataFrame van het scherm (id, tuin_id, afdeling,
      datum_teelt_start, datum_half, datum_oogst, oogstgewicht, lengte_eind,
      emmers); afgeronde teelten die niet in de historie staan komen erbij.
    - klimaat_afd: klimaat_per_afdeling(); teelten zonder klimaat op de
      plantdag vallen af.
    - geschatte_oogst(start) → de plandatum; een oogstdatum die daaraan gelijk
      is, is bij een import geschat en telt niet.
    """
    weken = {}
    for r in historie_week.itertuples():
        weken.setdefault(int(r.historie_id), {})[(int(r.isojaar), int(r.isoweek))] = (
            _getal(r.etmaal_temp), _getal(r.lichtsom_binnen))
    leerset = []
    for r in historie.itertuples():
        start, duur = _datum(r.startdatum), int(r.teeltduur_dagen)
        dagwaarden = {}
        for (j, w), (T, L) in weken.get(int(r.id), {}).items():
            if T is None or L is None:
                continue
            maandag = date.fromisocalendar(j, w, 1)
            for i in range(7):
                dagwaarden[maandag + timedelta(days=i)] = (T, L)
        reeks = dagreeks(start, duur, dagwaarden)
        if reeks is None:
            continue
        fg = _datum(r.florgib_datum)
        leerset.append({"tuin": int(r.tuin_id), "start": start, "duur": float(duur), "T": reeks[0], "L": reeks[1],
                        "florgib_dag": (fg - start).days if fg and start < fg else None,
                        "gewicht": _getal(r.oogstgewicht), "lengte": _getal(r.lengte_eind),
                        "precisie": r.oogst_precisie})
    in_historie = {int(x) for x in historie["teelt_id"].dropna()} if "teelt_id" in historie else set()
    for r in app_teelten.itertuples():
        start, oogst = _datum(r.datum_teelt_start), _datum(r.datum_oogst)
        if int(r.id) in in_historie or not start or not oogst or _getal(r.afdeling) is None:
            continue
        if geschatte_oogst(start) == oogst:
            continue
        duur = (oogst - start).days
        if not DUUR_GRENZEN[0] <= duur <= DUUR_GRENZEN[1]:
            continue
        reeks = dagreeks(start, duur, klimaat_afd.get((int(r.tuin_id), int(r.afdeling)), {}))
        if reeks is None:
            continue
        fg = _datum(r.datum_half)
        leerset.append({"tuin": int(r.tuin_id), "start": start, "duur": float(duur), "T": reeks[0], "L": reeks[1],
                        "florgib_dag": (fg - start).days if fg and start < fg < oogst else None,
                        "gewicht": _getal(r.oogstgewicht), "lengte": _getal(r.lengte_eind),
                        "precisie": "dag" if _getal(r.emmers) else "week"})
    return leerset


def weeklicht(historie_week, klimaat):
    """Meerjarig gemiddelde lichtsom binnen per ISO-week (alle jaren, afdelingen en tuinen samen)."""
    per_week = {}
    for r in historie_week.itertuples():
        if _getal(r.lichtsom_binnen) is not None:
            per_week.setdefault(int(r.isoweek), []).append(float(r.lichtsom_binnen))
    for r in klimaat.itertuples():
        if _getal(r.lichtsom) is not None:
            per_week.setdefault(_datum(r.datum).isocalendar()[1], []).append(float(r.lichtsom))
    gemiddeld = {w: float(np.mean(v)) for w, v in per_week.items()}
    if 53 not in gemiddeld and 52 in gemiddeld:
        gemiddeld[53] = gemiddeld[52]
    return gemiddeld


class TeeltPrognose:
    def __init__(self):
        self.model = None
        self.florgib_fractie = None
        self.gram_per_graad = None
        self.gram_betrouwbaar = None
        self.licht_per_week = {}
        self.n_leer = 0

    def fit(self, leerset, licht_per_week):
        self.model = MetTuinfactor(LineairModel()).fit(leerset)
        self.n_leer = len(leerset)
        fracties = [florgib_fractie(self.model.basis, t["T"], t["L"], t["florgib_dag"], t["duur"])
                    for t in leerset if t["florgib_dag"]]
        fracties = [f for f in fracties if f is not None]
        self.florgib_fractie = float(np.median(fracties)) if fracties else None
        self.licht_per_week = licht_per_week
        self._fit_gewicht(leerset)
        return self

    def _fit_gewicht(self, leerset):
        """Gram per °C boven de lichtlijn, gecorrigeerd voor lichtniveau (kleinste kwadraten)."""
        rijen = [(t["gewicht"], (t["T"] - t_ideaal(t["L"])).mean(), t["L"].mean()) for t in leerset if t["gewicht"]]
        if len(rijen) < 8:
            return
        y = np.array([r[0] for r in rijen])
        X = np.column_stack([np.ones(len(rijen)), [r[1] for r in rijen], [r[2] for r in rijen]])
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        self.gram_per_graad = float(coef[1])
        self.gram_betrouwbaar = len(rijen) >= 30

    def verwacht_licht(self, vanaf, dagen=TOEKOMST_DAGEN):
        waarden = [self.licht_per_week.get((vanaf + timedelta(days=i)).isocalendar()[1]) for i in range(dagen)]
        bekend = [w for w in waarden if w is not None]
        standaard = float(np.mean(bekend)) if bekend else 600.0
        return np.array([w if w is not None else standaard for w in waarden], float)

    def beoordeel(self, tuin, start, vandaag, plan, T_tot, L_tot, afwijking_nu, florgib=None):
        """
        Stand van één lopende teelt op `vandaag`.
        - T_tot/L_tot: werkelijke dagwaarden van planten t/m gisteren (van de eigen afdeling)
        - afwijking_nu: gemiddelde afwijking van de lichtlijn van de afdeling (laatste 14 dagen)
        - plan: plandatum oogst; florgib: geregistreerde Florgib-datum of None
        Geeft een dict met gedaan, florgib_verwacht, prognose (bij de huidige
        stooklijn), c (en of die begrensd is), prognose_bij_c en gewicht.
        """
        model = voor_tuin(self.model, tuin)
        k = len(T_tot)
        fg_dag = (florgib - start).days if florgib and start < florgib else None
        if fg_dag is not None and fg_dag <= k and self.florgib_fractie is not None:
            gedaan = self.florgib_fractie + ontwikkeling(model, T_tot[fg_dag:], L_tot[fg_dag:])
        else:
            gedaan = ontwikkeling(model, T_tot, L_tot)
        L_verw = self.verwacht_licht(vandaag)
        uit = {"gedaan": gedaan, "k": k, "L_verw": L_verw, "tuin": tuin, "start": start, "plan": plan,
               "afwijking_nu": afwijking_nu, "florgib_verwacht": None}

        def dag_bij(c, doel=1.0):
            """Voorspelde datum bij een constante afwijking c van de lichtlijn vanaf vandaag."""
            if gedaan >= doel:
                return vandaag
            rest = duur_uit_snelheid(model.snelheid(t_ideaal(L_verw) + c, L_verw), begin=gedaan, doel=doel)
            return None if rest is None else vandaag + timedelta(days=round(rest))

        uit["dag_bij"] = dag_bij
        # Verwachte Florgib: wanneer het model het mediane Florgib-deel bereikt.
        if fg_dag is None and self.florgib_fractie is not None:
            if gedaan >= self.florgib_fractie:
                dag = duur_uit_snelheid(model.snelheid(T_tot, L_tot), doel=self.florgib_fractie)
                uit["florgib_verwacht"] = start + timedelta(days=round(dag)) if dag else None
            else:
                uit["florgib_verwacht"] = dag_bij(afwijking_nu if afwijking_nu is not None else 0.0,
                                                  doel=self.florgib_fractie)
        uit["prognose"] = dag_bij(afwijking_nu if afwijking_nu is not None else 0.0)
        uit["oogstrijp"] = gedaan >= 1
        # Benodigde correctie voor de plandatum (niet meer zinvol als de teelt al rijp is).
        resterend = (plan - vandaag).days if plan else None
        if resterend is None or uit["oogstrijp"]:
            uit.update(c=None, begrensd=False, prognose_bij_c=None)
        elif resterend <= 0 and gedaan < 1:
            uit.update(c=C_GRENZEN[1], begrensd=True, prognose_bij_c=dag_bij(C_GRENZEN[1]))
        else:
            c, begrensd = benodigde_correctie(model, gedaan, [], [], L_verw, max(resterend, 0), C_GRENZEN)
            uit.update(c=c, begrensd=begrensd, prognose_bij_c=dag_bij(c) if begrensd else plan)
        uit["gewicht"] = self.gewichtseffect(uit["c"])
        return uit

    def gewichtseffect(self, c):
        if c is None or self.gram_per_graad is None:
            return None
        return c * self.gram_per_graad


def afwijking_afdeling(dagen_afd, vandaag, venster=AFWIJKING_VENSTER_DAGEN):
    """Gemiddelde afwijking van de lichtlijn over de laatste `venster` dagen met data vóór vandaag."""
    waarden = [T - t_ideaal(L) for d, (T, L) in sorted(dagen_afd.items()) if d < vandaag][-venster:]
    return float(np.mean(waarden)) if waarden else None


def op_koers(c):
    return c is not None and abs(c) < OP_KOERS_MARGE


def c_klasse(c, begrensd=False):
    """Kleurklasse voor het vakblok: blauw bij negatieve c, neutraal rond 0, oranje→rood bij positieve c."""
    if c is None:
        return "grijs"
    if abs(c) < OP_KOERS_MARGE:
        return "n"
    grenzen = [(-1.5, "b3"), (-0.75, "b2"), (0, "b1"), (0.75, "o1"), (1.5, "o2"), (2.25, "r1")]
    for grens, klasse in grenzen:
        if c < grens:
            return klasse
    return "r2"


def afdelingsadvies(vakken):
    """
    vakken: [{vak, c, gewicht_stelen}] van één afdeling (alleen vakken met een c).
    Geeft (advies, doorslag): het gewogen gemiddelde van c naar aantal stelen,
    en het vak dat daar het meest aan bijdraagt (gewicht × |c|).
    """
    bruikbaar = [v for v in vakken if v["c"] is not None and v["stelen"]]
    if not bruikbaar:
        return None, None
    totaal = sum(v["stelen"] for v in bruikbaar)
    advies = sum(v["c"] * v["stelen"] for v in bruikbaar) / totaal
    doorslag = max(bruikbaar, key=lambda v: v["stelen"] * abs(v["c"]))["vak"]
    return advies, doorslag
