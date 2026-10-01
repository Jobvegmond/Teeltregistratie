# UI-standaard

Eén manier van werken voor elke pagina van de Teeltregistratie. Nieuwe of aangepaste pagina's
gebruiken alleen de componenten uit `ui/` en volgen de vaste paginaopbouw hieronder.

## 1. Paginaopbouw

Elke pagina, van boven naar beneden:

| | Onderdeel | Component |
|---|---|---|
| a | Titel + knop **Uitleg** rechts ernaast | `layout.pagina_kop()` |
| b | Eén filterbalk (één regel, loopt door op een smal scherm) | `layout.filterbalk()` + `ui/filters.py` |
| c | Samenvatting (tabel) | `layout.sectie()` |
| d | Hoofdweergave (matrix, tabel of grafiek), met legenda eronder | `legend.legenda()` |
| e | Aanvullende lijsten in openklapmenu's | `layout.uitklap()` |
| f | Export | `layout.export()` |

Een onderdeel dat een pagina niet heeft, valt weg. De volgorde blijft.

```python
from ui import filters, layout, legend
from ui import help as uitleg_help

layout.pagina_kop(
    "Watergift",
    wat="Per vak per dag de watergift (l/m²) ...",
    lezen=["Weken lopen van zondag t/m zaterdag.", "Klik op een vak voor het vak ..."],
    bron="Priva (API), elke ochtend opgehaald ...",
    kleuren="Blauw = watergift ...",
)
balk = layout.filterbalk("watergift")
lengte, eind_zo = filters.periode("wg_periode", ["2 wk", "4 wk", "3 mnd"], "4 wk", ..., plek=balk)
afdelingen = filters.afdelingen("afd_t3", ["1", "3", "4", "2"], plek=balk)
vooruit = filters.schakelaar("Vooruitkijken", "wg_vooruit", True, plek=balk)
...                                   # hoofdweergave
legend.legenda(wg_matrix.LEGENDA)
layout.export(excel, "watergift_tuin_3.xlsx")
```

## 2. Eén element per soort keuze

| Soort keuze | Element | Component |
|---|---|---|
| Tuin | Alleen de globale keuze in de kop (Tuin 1 / Tuin 3 / Beide). Nooit een tuinfilter op een pagina. | `filters.tuin()` (in app.py, per pagina een modus in `TUIN_MODUS`) |
| Periode (kalender) | Knoppengroep voor de lengte + ◀ [label ▾] ▶; klik op het label om te springen | `filters.periode()` |
| Teelt (plantweek), pootweek | ◀ [Teelt wk 33 '26 · 8 vakken ▾] ▶ | `filters.bladeraar()` |
| Afdeling | Pills, meervoudig, teeltvolgorde, standaard alles aan | `filters.afdelingen()` (in app.py: `afdeling_filters()`) |
| Overige filters (ras, categorie, type, gebruiker) | Pills bij ≤ 8 opties, anders keuzelijst met meervoudige keuze; niets gekozen = alles | `filters.keuzes()` |
| Eén keuze uit een lange lijst (welke tabel) | Keuzelijst, altijd één gekozen | `filters.keuze()` |
| Zoeken | Eén tekstveld, alleen op registerpagina's, altijd als laatste in de filterbalk | `filters.zoekveld()` |
| Weergave-optie (eenheid, vergelijk met) | Knoppengroep, altijd één gekozen; nooit radio | `filters.weergave()` |
| Aan/uit (Vooruitkijken, Alle concepten tonen) | Schakelaar | `filters.schakelaar()` |
| Datum | Alleen in invoerformulieren (zijbalk, Planning), nooit om te filteren | `st.date_input` |

Niet voor filters: `st.slider`, `st.select_slider`, `st.radio`, `st.date_input`, `st.number_input`.
Een schuif mag alleen voor een doorlopende instelwaarde in een formulier of popup (rijpheid bij de
oogst, de afdelingscorrectie in het stookadvies), nooit om weken of perioden te kiezen.

### Tuin per pagina

`TUIN_MODUS` in app.py zegt per pagina wat de tuinkeuze doet:

- **vrij** (standaard): Tuin 1 / Tuin 3 / Beide.
- **een**: de pagina werkt per tuin (Planning, Stek, Meer). Beide staat er niet bij; stond Beide aan,
  dan toont de pagina de laatst gekozen tuin met de melding "Beide kan hier niet".
- **beide**: de pagina gaat altijd over beide tuinen (Tuin vergelijking); keuze uitgeschakeld met reden.

Registreren kan maar in één tuin: bij Beide vraagt de zijbalk "Registreren in".

### Keuzes bewaren

Elke keuze staat in `st.session_state["f_<sleutel>"]`, niet in de widget-key: Streamlit ruimt de
state van een widget op zodra die een keer niet getekend wordt. Zo blijft een keuze staan als je van
pagina wisselt. Gebruik dezelfde sleutel waar de keuze hetzelfde betekent (afdeling: `afd_t<tuin>`
op Teeltoverzicht en Watergift) en een eigen sleutel waar niet.

Doorklikken naar een andere pagina met de juiste filters gaat met `ga_naar(url_path, {sleutel: waarde})`
in app.py; `None` zet een filter terug op de standaard.

### Voorbeelden

```python
# Periode: lengte + ◀ [label ▾] ▶
lengte, sleutel = filters.periode(
    "tv_periode", perioden.PERIODEN, "Week",
    opties_van=lambda n: perioden.reeks(eerste, vandaag, n),        # laag → hoog
    standaard_van=lambda n: perioden.laatste_volledige(n, vandaag),
    format_van=lambda n: lambda k: perioden.periode_label(k, n),
    huidig_van=lambda n: perioden.periode_sleutel(vandaag, n)[0], plek=balk)

# Teelt: ◀ [label ▾] ▶ over een lijst
week = filters.bladeraar("tl_teelt", plantweken, standaard, naam="teelt", plek=balk,
                         format_func=lambda w: f"Teelt wk {w[1]} '{str(w[0])[2:]} · {n[w]} vakken")

# Overige filters, zoeken, weergave, schakelaar
rassen = filters.keuzes("Ras", ["Cameron", "..."], "reg_ras", plek=balk)
zoek = filters.zoekveld("reg_zoek", "Vak of code", plek=balk)
soort = filters.weergave("Vergelijk met", ("vorig_jaar", "vorige"), "tv_vergelijk", "vorig_jaar", plek=balk)
alles = filters.schakelaar("Alle concepten tonen", "planning_alles", False, plek=balk)
```

## 3. Uitleg op één manier

- De knop **Uitleg** naast de titel opent een popover met altijd dezelfde kopjes:
  *Wat zie je · Hoe lees je het · Waar komen de getallen vandaan · Wat betekenen de kleuren*
  (`uitleg_help.uitleg()`, via `layout.pagina_kop()`). Een kopje zonder tekst valt weg.
- ⓘ-tooltips alleen bij losse kengetallen en kolomkoppen (`help=`).
- Onder een tabel of grafiek hooguit één korte regel: `uitleg_help.voetnoot()`. Langere tekst gaat
  naar de Uitleg.
- Geen "Hoe lees ik dit?"-openklapmenu's en geen aparte uitlegpagina.

## 4. Eén thuis per soort informatie

| Informatie | Thuis | Elders |
|---|---|---|
| Details van een vak | De vakpopup `vak_venster()` | Overal dezelfde popup (matrix, register, Teeltvergelijking, Opmerkingen, Watergift, missers) |
| Watergift per vak | Pagina Watergift | Vakpopup (staafjes op de tijdlijn + tabel Watergift per dag) |
| Lijst van vakken | Vakkenregister (Teeltoverzicht) | Doorklik-link met het juiste filter |
| Opmerkingen | Pagina Opmerkingen | Vakpopup; elders één regel "n opmerkingen →" |
| Vooruitblik | Planning | – |

## 5. Legenda's

Elke matrix of grafiek met kleuren of symbolen heeft direct eronder een zichtbare legenda:
`legend.legenda(items)`. Altair-grafieken met een eigen legenda zetten die onder de grafiek
(`orient="bottom"`).

```python
legend.legenda([
    {"kleur": "#5b9bd5", "label": "watergift (l/m²)"},
    {"kleur": "#8e44ad", "vorm": "stip", "label": "Florgib"},
    {"kleur": "#8e44ad", "vorm": "ring", "label": "verwachte Florgib"},
    {"kleur": "#e34948", "vorm": "stippelrand", "label": "overlap"},
], titel="Prognose t.o.v. plan (d):")
```

Vormen: `blok` (standaard), `rand`, `stippelrand`, `lijn`, `stip`, `ring`, `ruit`; extra CSS via `stijl`.

## 6. Weken

De week loopt in de hele app van **zondag t/m zaterdag** (`logic/weken.py`): het weeknummer is dat van
de ISO-week die op de maandag erna begint. Teeltcodes, plantweken en pootweken blijven de ISO-week van
de plantdatum. Gebruik voor kalenderweken altijd `logic.weken` (of `logic.perioden` met "Week"),
nooit `isocalendar()` direct.
