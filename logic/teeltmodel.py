"""
Teeltduurmodellen als ontwikkelingssnelheid per dag.

Elke dag telt een deel van de teelt af: snelheid r(T, L) per dag, met T de
etmaaltemperatuur en L de lichtsom binnen van die dag. Een teelt (of fase)
is klaar zodra de opgetelde snelheid 1 bereikt. Zo werken dezelfde modellen
voor een afgeronde teelt (terugrekenen), een prognose (werkelijke dagen tot nu
plus verwachte dagen daarna) en de correctie c (welke constante afwijking van
de lichtlijn brengt de teelt precies op de plandatum).

Modellen
- LineairModel:      r = a + b·L + c·(T − T_ideaal(L))
                     Gefit als 1/teeltduur = a + b·gem(L) + c·gem(afwijking): de
                     gemiddelde dagsnelheid is precies 1/teeltduur. Licht en de
                     afwijking van de lichtlijn staan erin, niet T en L naast
                     elkaar (die lopen door de stookstrategie bijna gelijk op).
- GraaddagenModel:   r = (max(T − Tbasis, 0) + κ·L/100) / G
                     G = de mediaan van de opgebouwde som bij de oogst; κ = 0 is
                     het zuivere graaddagenmodel, κ > 0 telt licht mee.

Parameters komen altijd uit de data (fit); er staan hier geen vaste getallen
voor de teelt in. Alles werkt op numpy-arrays per dag vanaf de plantdag.
"""
import math

import numpy as np

from logic.lichtlijn import t_ideaal

MIN_SNELHEID = 1e-4   # nooit 0 of negatief: anders "nooit rijp"


def duur_uit_snelheid(snelheid, begin=0.0, doel=1.0):
    """
    Aantal dagen (met fractie) tot de opgetelde snelheid, vanaf `begin`
    (al opgebouwd deel), `doel` bereikt (1 = oogstrijp; een fractie, bijv. het
    deel waarop de Florgib valt). None als dat binnen de reeks niet lukt.
    """
    r = np.maximum(np.asarray(snelheid, dtype=float), MIN_SNELHEID)
    som = begin + np.cumsum(r)
    klaar = np.nonzero(som >= doel)[0]
    if not len(klaar):
        return None
    i = int(klaar[0])
    over = som[i] - doel           # deel van dag i dat al niet meer nodig was
    return i + 1 - over / r[i]


def ontwikkeling(model, T, L):
    """Opgebouwd deel van de teelt (1 = oogstrijp) na de dagen in T/L."""
    if not len(T):
        return 0.0
    return float(np.maximum(model.snelheid(T, L), MIN_SNELHEID).sum())


def florgib_fractie(model, T, L, florgib_dag, duur):
    """
    Deel van de ontwikkeling dat de teelt had bereikt op de Florgib-dag,
    genormeerd op de werkelijke oogst: som tot de Florgib / som tot de oogst.
    Onafhankelijk van een tuinfactor (die valt weg in de deling).
    """
    totaal = ontwikkeling(model, T[:int(round(duur))], L[:int(round(duur))])
    return ontwikkeling(model, T[:florgib_dag], L[:florgib_dag]) / totaal if totaal else None


class LineairModel:
    naam = "regressie (licht + afwijking lichtlijn)"

    def __init__(self):
        self.a = self.b = self.c = None

    def snelheid(self, T, L):
        T, L = np.asarray(T, float), np.asarray(L, float)
        return self.a + self.b * L + self.c * (T - t_ideaal(L))

    def fit(self, teelten):
        """teelten: dicts met T, L (arrays vanaf plantdag) en duur (dagen)."""
        X, y = [], []
        for t in teelten:
            n = int(round(t["duur"]))
            L, T = t["L"][:n], t["T"][:n]
            X.append([1.0, L.mean(), (T - t_ideaal(L)).mean()])
            y.append(1.0 / t["duur"])
        (self.a, self.b, self.c), *_ = np.linalg.lstsq(np.array(X), np.array(y), rcond=None)
        return self

    def dagen_per_graad(self, lichtsom, afwijking=0.0):
        """Teeltduur bij een vaste lichtsom en afwijking van de lichtlijn (voor 'dagen per °C')."""
        r = self.a + self.b * lichtsom + self.c * afwijking
        return 1.0 / r if r > 0 else math.inf


class GraaddagenModel:
    def __init__(self, t_basis, kappa=0.0):
        self.t_basis, self.kappa, self.G = t_basis, kappa, None
        self.naam = (f"graaddagen Tbasis {t_basis:g} °C" + (f" + licht (κ {kappa:g})" if kappa else ""))

    def _eenheden(self, T, L):
        T, L = np.asarray(T, float), np.asarray(L, float)
        return np.maximum(T - self.t_basis, 0.0) + self.kappa * L / 100.0

    def snelheid(self, T, L):
        return self._eenheden(T, L) / self.G

    def som_bij_oogst(self, t):
        n = int(round(t["duur"]))
        return float(self._eenheden(t["T"][:n], t["L"][:n]).sum())

    def fit(self, teelten):
        self.G = float(np.median([self.som_bij_oogst(t) for t in teelten]))
        return self

    def dagen_per_graad(self, lichtsom, afwijking=0.0):
        r = self.snelheid([t_ideaal(lichtsom) + afwijking], [lichtsom])[0]
        return 1.0 / r if r > 0 else math.inf


class MetTuinfactor:
    """
    Een model met een correctie per tuin: de snelheid wordt per tuin gedeeld
    door de mediaan van de opgebouwde som bij de oogst in die tuin (1 = geen
    verschil). Een tuin die structureel trager is dan het model krijgt zo een
    factor > 1. Gebruik voor_tuin(tuin) om met de correctie te rekenen.
    """

    def __init__(self, basis):
        self.basis, self.factor = basis, {}
        self.naam = basis.naam + " + tuincorrectie"

    def fit(self, teelten):
        self.basis.fit(teelten)
        sommen = {}
        for t in teelten:
            n = int(round(t["duur"]))
            sommen.setdefault(t["tuin"], []).append(
                float(np.maximum(self.basis.snelheid(t["T"][:n], t["L"][:n]), MIN_SNELHEID).sum()))
        self.factor = {tuin: float(np.median(v)) for tuin, v in sommen.items()}
        return self

    def voor_tuin(self, tuin):
        return _Geschaald(self.basis, self.factor.get(tuin, 1.0))

    def snelheid(self, T, L):
        return self.basis.snelheid(T, L)


class _Geschaald:
    def __init__(self, basis, factor):
        self.basis, self.factor, self.naam = basis, factor, basis.naam

    def snelheid(self, T, L):
        return self.basis.snelheid(T, L) / self.factor

    def dagen_per_graad(self, lichtsom, afwijking=0.0):
        return self.basis.dagen_per_graad(lichtsom, afwijking) * self.factor


def voor_tuin(model, tuin):
    """Het model zoals het voor deze tuin rekent (met tuincorrectie als het model die heeft)."""
    return model.voor_tuin(tuin) if hasattr(model, "voor_tuin") else model


def voorspel_duur(model, T, L, begin=0.0):
    """Teeltduur (dagen vanaf de plantdag, of vanaf het begin van de reeks) volgens het model."""
    return duur_uit_snelheid(model.snelheid(T, L), begin)


def leave_one_out(maak_model, teelten):
    """
    Voorspelde duur per teelt, telkens met een model dat zonder die teelt is
    gefit. `maak_model()` levert een nieuw, ongefit model. De teelt zelf wordt
    voorspeld met zijn werkelijke dagreeks (T_ext/L_ext loopt door na de
    oogst, voor als het model later uitkomt).
    """
    voorspeld = []
    for i, t in enumerate(teelten):
        model = maak_model().fit(teelten[:i] + teelten[i + 1:])
        voorspeld.append(voorspel_duur(voor_tuin(model, t["tuin"]), t["T_ext"], t["L_ext"]))
    return np.array([np.nan if v is None else v for v in voorspeld])


def benodigde_correctie(model, gedaan, T_gedaan, L_gedaan, L_toekomst, resterend_dagen, grenzen=(-2.0, 3.0),
                        tolerantie=0.01):
    """
    De constante afwijking c van de lichtlijn waarmee de teelt precies na
    `resterend_dagen` klaar is: T_dag = T_ideaal(L_dag) + c voor alle
    resterende dagen (L_toekomst = verwachte lichtsom per dag). Opgelost met
    bisectie tussen de grenzen. Geeft (c, begrensd): begrensd is True als c
    buiten de grenzen zou liggen (c staat dan op de grens).

    `gedaan` is het al opgebouwde deel (0..1) als dat al bekend is; anders
    wordt het uit T_gedaan/L_gedaan berekend.
    """
    if gedaan is None:
        gedaan = float(np.maximum(model.snelheid(T_gedaan, L_gedaan), MIN_SNELHEID).sum()) if len(T_gedaan) else 0.0
    L_toekomst = np.asarray(L_toekomst, float)

    def rest_bij(c):
        """Nog te gaan na `resterend_dagen` dagen met afwijking c (negatief = te vroeg klaar)."""
        n = max(int(math.floor(resterend_dagen)), 0)
        frac = resterend_dagen - n
        r = np.maximum(model.snelheid(t_ideaal(L_toekomst) + c, L_toekomst), MIN_SNELHEID)
        opgebouwd = r[:n].sum() + (r[n] * frac if n < len(r) else 0.0)
        return 1.0 - gedaan - opgebouwd

    laag, hoog = grenzen
    if rest_bij(hoog) > 0:        # zelfs op de bovengrens niet op tijd
        return hoog, True
    if rest_bij(laag) < 0:        # zelfs op de ondergrens te vroeg
        return laag, True
    while hoog - laag > tolerantie:
        midden = (laag + hoog) / 2
        if rest_bij(midden) > 0:
            laag = midden
        else:
            hoog = midden
    return (laag + hoog) / 2, False
