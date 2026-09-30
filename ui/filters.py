"""
Eén element per soort keuze (UI-standaard, docs/ui-standaard.md). Pagina's
gebruiken voor filters alleen deze functies, nooit losse st.slider, st.radio of
st.date_input.

  tuin()        globale tuinkeuze in de kop (Tuin 1 / Tuin 3 / Beide)
  periode()     knoppengroep voor de lengte + ◀ [label ▾] ▶ (kalender)
  bladeraar()   ◀ [label ▾] ▶ over een lijst (teelt/plantweek, pootweek, …)
  afdelingen()  pills, meervoudig, teeltvolgorde, standaard alles aan
  keuzes()      overige filters: pills bij ≤ 8 opties, anders keuzelijst
  zoekveld()    één tekstveld, alleen op registerpagina's, altijd als laatste
  weergave()    weergave-optie (eenheid, vergelijk met): knoppengroep
  schakelaar()  aan/uit-optie

Elke keuze staat in st.session_state onder "f_<sleutel>" (niet de widget-key),
zodat hij bewaard blijft als je van pagina wisselt: Streamlit ruimt de state
van een widget op zodra die een keer niet getekend wordt. Gebruik dezelfde
sleutel op pagina's waar de keuze hetzelfde betekent (tuin altijd; afdeling
per tuin), en een eigen sleutel waar niet.
"""
import streamlit as st

MAX_PILLS = 8


# --- bewaren over pagina's heen ---


def opslag(sleutel):
    return f"f_{sleutel}"


def bewaard(sleutel, standaard=None):
    """De bewaarde keuze (of `standaard`)."""
    return st.session_state.get(opslag(sleutel), standaard)


def bewaar(sleutel, waarde):
    st.session_state[opslag(sleutel)] = waarde


def _klaarzetten(sleutel, standaard, geldig=lambda w: True):
    """Bewaarde waarde (geldig, anders `standaard`) → widget-state; geeft de widget-key terug."""
    o, w = opslag(sleutel), f"w_{sleutel}"
    if o not in st.session_state or not geldig(st.session_state[o]):
        st.session_state[o] = standaard
    st.session_state[w] = st.session_state[o]
    return w


def _kopieer(sleutel, leeg=None):
    """on_change: widget → opslag. Een lege keuze (knop uitgeklikt) wordt `leeg`, of blijft de oude bij None."""
    def bij_wijziging():
        waarde = st.session_state.get(f"w_{sleutel}")
        if waarde is None or waarde == []:
            if leeg is None:
                return
            waarde = leeg
        st.session_state[opslag(sleutel)] = waarde
    return bij_wijziging


# --- tuin (kop) ---


def tuin(tuinen, modus="vrij", reden=None, plek=None):
    """
    De globale tuinkeuze in de kop; `tuinen` = [(nummer, naam)] laag → hoog.

    modus "vrij":  Tuin 1 / Tuin 3 / Beide.
    modus "een":   de pagina werkt per tuin; Beide staat er niet bij. Stond
                   Beide aan, dan toont de pagina de laatst gekozen tuin (en
                   blijft Beide bewaard voor pagina's die het wel kunnen).
    modus "beide": de pagina gaat altijd over beide tuinen; keuze uitgeschakeld.
    modus "geen":  tuin is hier niet van toepassing; keuze uitgeschakeld.

    Bewaart "tuin_nummer" (laatst gekozen enkele tuin) en "tuin_weergave"
    (nummer of "beide"). Geeft (weergave, nummer) voor deze pagina terug.
    """
    plek = plek or st
    nummers = [n for n, _ in tuinen]
    namen = dict(tuinen)
    ss = st.session_state
    if ss.get("tuin_nummer") not in nummers:
        ss["tuin_nummer"] = nummers[0]
    if ss.get("tuin_weergave") not in nummers + ["beide"]:
        ss["tuin_weergave"] = ss["tuin_nummer"]

    def naam(n):
        return "Beide" if n == "beide" else namen.get(n, f"Tuin {n}")

    if len(nummers) < 2:
        return nummers[0], nummers[0]
    if modus in ("beide", "geen"):
        opties = nummers + ["beide"]
        ss["w_tuin_vast"] = "beide" if modus == "beide" else None
        plek.segmented_control("Tuin", opties, format_func=naam, key="w_tuin_vast", disabled=True,
                               label_visibility="collapsed", width="content",
                               help=reden or ("Deze pagina gaat over beide tuinen." if modus == "beide"
                                              else "Tuin is hier niet van toepassing."))
        return ("beide", ss["tuin_nummer"]) if modus == "beide" else (None, ss["tuin_nummer"])

    def gekozen():
        waarde = ss.get(f"w_tuin_{modus}")
        if waarde is None:
            return
        ss["tuin_weergave"] = waarde
        if waarde != "beide":
            ss["tuin_nummer"] = waarde

    opties = nummers + (["beide"] if modus == "vrij" else [])
    weergave = ss["tuin_weergave"] if modus == "vrij" else ss["tuin_nummer"]
    ss[f"w_tuin_{modus}"] = weergave
    plek.segmented_control("Tuin", opties, format_func=naam, key=f"w_tuin_{modus}", on_change=gekozen,
                           label_visibility="collapsed", width="content",
                           help=reden if modus == "een" and ss["tuin_weergave"] == "beide" else None)
    return weergave, ss["tuin_nummer"]


# --- bladeren: ◀ [label ▾] ▶ ---


def bladeraar(sleutel, opties, standaard, format_func=str, huidig=None, plek=None, breedte=None,
              naam="periode", spring_label="Spring naar"):
    """
    ◀ [label ▾] ▶ over `opties` (chronologisch, laag → hoog). Klik op het label
    voor een keuzelijst om direct te springen (en "Naar nu" als `huidig` is
    gegeven). Geeft de gekozen optie terug.
    """
    plek = plek or st
    opties = list(opties)
    if not opties:
        return None
    o = opslag(sleutel)
    if st.session_state.get(o) not in opties:
        st.session_state[o] = standaard if standaard in opties else opties[-1]
    waarde = st.session_state[o]
    i = opties.index(waarde)

    def zet(nieuw):
        st.session_state[o] = nieuw

    def gesprongen():
        st.session_state[o] = st.session_state[f"w_{sleutel}_spring"]

    rij = plek.container(horizontal=True, vertical_alignment="center", gap="small", width="content",
                         key=f"bladeraar_{sleutel}")
    rij.button("◀", key=f"w_{sleutel}_terug", on_click=zet, args=(opties[max(i - 1, 0)],), disabled=i == 0,
               help=f"Vorige {naam}")
    with rij.popover(format_func(waarde), width=breedte or "content"):
        st.session_state[f"w_{sleutel}_spring"] = waarde
        st.selectbox(spring_label, opties, format_func=format_func, key=f"w_{sleutel}_spring", on_change=gesprongen)
        if huidig is not None and huidig in opties and huidig != waarde:
            st.button("Naar nu", key=f"w_{sleutel}_nu", on_click=zet, args=(huidig,))
    rij.button("▶", key=f"w_{sleutel}_verder", on_click=zet, args=(opties[min(i + 1, len(opties) - 1)],),
               disabled=i == len(opties) - 1, help=f"Volgende {naam}")
    return waarde


def periode(sleutel, lengtes, standaard_lengte, opties_van, standaard_van, format_van=None, huidig_van=None,
            label="Periode", plek=None, per_lengte=True, breedte=None):
    """
    Kalenderperiode: knoppengroep voor de lengte (bijv. Week / Maand / Kwartaal /
    Jaar, of 2 wk / 4 wk / 3 mnd) + ◀ [label ▾] ▶. De functies krijgen de
    gekozen lengte mee: opties_van(lengte) = de perioden (laag → hoog),
    standaard_van(lengte), format_van(lengte) → format_func, huidig_van(lengte).
    Geeft (lengte, periode) terug. De periode wordt per lengte apart bewaard,
    of bij per_lengte=False één keer (als de opties niet van de lengte afhangen).
    """
    plek = plek or st
    lengte = weergave(label, lengtes, f"{sleutel}_lengte", standaard_lengte, plek=plek)
    kies = bladeraar(f"{sleutel}_{lengte}" if per_lengte else sleutel, opties_van(lengte), standaard_van(lengte),
                     format_func=(format_van(lengte) if format_van else str),
                     huidig=huidig_van(lengte) if huidig_van else None, plek=plek, breedte=breedte)
    return lengte, kies


# --- afdeling en overige filters ---


def afdelingen(sleutel, opties, label="Afdeling", plek=None, format_func=None):
    """
    Afdelingen als labels die je aan- en uitzet, in de volgorde van `opties`
    (teeltvolgorde), standaard alles aan. Klik je de laatste uit, dan gaan ze
    weer allemaal aan. Geeft de gekozen afdelingen terug, in teeltvolgorde.
    """
    plek = plek or st
    opties = list(opties)
    w = _klaarzetten(sleutel, opties, geldig=lambda v: isinstance(v, list) and v and set(v) <= set(opties))
    plek.pills(label, opties, selection_mode="multi", key=w, on_change=_kopieer(sleutel, leeg=opties),
               format_func=format_func or (lambda a: f"Afd. {a}"), width="content")
    gekozen = set(bewaard(sleutel))
    return [a for a in opties if a in gekozen]


def keuzes(label, opties, sleutel, plek=None, format_func=str, placeholder=None):
    """
    Overige filters (ras, categorie, type, gebruiker): pills bij ≤ 8 opties,
    anders een keuzelijst met meervoudige keuze. Niets gekozen = alles.
    Geeft de gekozen opties terug (leeg = geen filter).
    """
    plek = plek or st
    opties = list(opties)
    w = _klaarzetten(sleutel, [], geldig=lambda v: isinstance(v, list) and set(v) <= set(opties))
    if len(opties) <= MAX_PILLS:
        plek.pills(label, opties, selection_mode="multi", key=w, on_change=_kopieer(sleutel, leeg=[]),
                   format_func=format_func, width="content")
    else:
        plek.multiselect(label, opties, key=w, on_change=_kopieer(sleutel, leeg=[]), format_func=format_func,
                         placeholder=placeholder or f"Alle ({len(opties)})", width=220)
    return list(bewaard(sleutel, []))


def zoekveld(sleutel, placeholder="Zoeken", label="Zoeken", plek=None):
    """Eén tekstveld, alleen op registerpagina's, altijd als laatste in de filterbalk."""
    plek = plek or st
    w = _klaarzetten(sleutel, "")
    plek.text_input(label, key=w, on_change=_kopieer(sleutel, leeg=""), placeholder=placeholder, width=220)
    return bewaard(sleutel, "").strip()


# --- weergave en aan/uit ---


def weergave(label, opties, sleutel, standaard, plek=None, format_func=str, label_zichtbaar=True):
    """Weergave-optie als knoppengroep (nooit radio); er is altijd één gekozen."""
    plek = plek or st
    opties = list(opties)
    w = _klaarzetten(sleutel, standaard, geldig=lambda v: v in opties)
    plek.segmented_control(label, opties, key=w, on_change=_kopieer(sleutel), format_func=format_func,
                           width="content", label_visibility="visible" if label_zichtbaar else "collapsed")
    return bewaard(sleutel, standaard)


def schakelaar(label, sleutel, standaard=False, plek=None, help=None):
    """Aan/uit-optie (Vooruitkijken, Alles tonen)."""
    plek = plek or st
    w = _klaarzetten(sleutel, bool(standaard), geldig=lambda v: isinstance(v, bool))

    def bij_wijziging():
        st.session_state[opslag(sleutel)] = bool(st.session_state.get(w))

    plek.toggle(label, key=w, on_change=bij_wijziging, help=help)
    return bewaard(sleutel, bool(standaard))
