"""
De CSS van de hele app, op één plek. laad() zet hem bovenaan elke run neer (ook op het inlogscherm); de
vergelijkingstabellen (ui/vergelijkingstabel.py) gebruiken de klassen .vt-*.

Vormgeving (docs/ui-standaard.md, §7): strak en licht. Knoppen, keuzegroepen en velden zijn zacht grijsgroen
gevuld in plaats van omlijnd; een keuzegroep (navigatie, tuin, weergave) is één "spoor" waarin de gekozen optie
wit oplicht. Ronding 0,5 rem (theme in .streamlit/config.toml), weinig witruimte tussen de blokken.

Licht en donker: de kleuren staan als CSS-variabelen in :root (PALET), per thema. Alleen de vaste kopregel en
eerste kolom van een vergelijkingstabel hebben een dekkende achtergrond nodig (anders schuift de tabel er
zichtbaar onderdoor); die komt uit het actieve thema (--vt-bg).
"""
import streamlit as st

# Per thema: achtergrond, vlak (velden, sporen, tegels), rand, zachte tekst, groen en het lichte groen, de
# gekozen optie in een spoor en de schaduw daarvan. Gelijk aan .streamlit/config.toml.
PALET = {
    "light": {"pagina": "#f9faf9", "bg": "#ffffff", "vlak": "#eef0ef", "vlak-hover": "#e4e7e5", "rand": "#e4e7e5",
              "zacht": "rgba(24, 32, 27, 0.6)", "groen": "#0A562C", "groen-donker": "#074020",
              "groen-zacht": "rgba(10, 86, 44, 0.09)", "oranje": "#F8992D", "gekozen": "#ffffff",
              "logo-bg": "transparent", "logo-pad": "0",
              "schaduw": "0 1px 2px rgba(16, 24, 20, 0.10), 0 1px 1px rgba(16, 24, 20, 0.06)"},
    "dark": {"pagina": "#0e1210", "bg": "#171c19", "vlak": "#222925", "vlak-hover": "#2b332e", "rand": "#2c3530",
             "zacht": "rgba(230, 235, 232, 0.6)", "groen": "#4e9e75", "groen-donker": "#3f8a63",
             "groen-zacht": "rgba(78, 158, 117, 0.16)", "oranje": "#F8992D", "gekozen": "#2f3a34",
             "logo-bg": "#ffffff", "logo-pad": "0.3rem 0.45rem",
             "schaduw": "0 1px 2px rgba(0, 0, 0, 0.45)"},
}

# Het logo en het bloemetje van Van Egmond Matricaria (van tanacetum.nl), uit static/ (server.enableStaticServing).
# Als <img>, zodat de opmaak in de SVG's niet in de app lekt.
LOGO = '<img class="vem-logo-vol" src="/app/static/logo-vem.svg" alt="Van Egmond Matricaria">'
BLOEM = '<img class="vem-bloem" src="/app/static/bloem-vem.svg" alt="">'

CSS = """
/* ---------- Ruimte ---------- */
/* Geen eigen balk van Streamlit bovenin (de app heeft een eigen kop): de inhoud begint direct bovenaan, met
   minder ruimte aan de zijkanten. */
header[data-testid="stHeader"] { display: none; }
[data-testid="stMainBlockContainer"], .block-container {
    padding-top: 1rem !important; padding-bottom: 3rem !important;
    padding-left: 2rem !important; padding-right: 2rem !important;
}
@media (max-width: 700px) {
    [data-testid="stMainBlockContainer"], .block-container {
        padding-left: 0.75rem !important; padding-right: 0.75rem !important; padding-top: 0.6rem !important;
    }
}
/* Lichtgrijze achtergrond; tabellen, grafieken, openklapmenu's en tegels staan er als witte kaarten op. */
.stApp, [data-testid="stApp"], [data-testid="stAppViewContainer"], [data-testid="stMain"] { background: var(--vem-pagina); }
/* Grafieken als witte kaart. Een grafiek neemt de volle breedte van zijn blok, dus binnenruimte zou hem over
   de rand duwen: de witte rand en de lijn zijn een schaduw buiten de grafiek, die geen ruimte inneemt. */
[data-testid="stVegaLiteChart"], [data-testid="stArrowVegaLiteChart"] {
    background: var(--vem-bg); border-radius: 0.4rem;
    box-shadow: 0 0 0 8px var(--vem-bg), 0 0 0 9px var(--vem-rand);
}
[data-testid="stElementContainer"]:has([data-testid="stVegaLiteChart"]),
[data-testid="stElementContainer"]:has([data-testid="stArrowVegaLiteChart"]) { margin: 12px 9px 8px; width: calc(100% - 18px) !important; }
[data-testid="stForm"] {
    background: var(--vem-bg); border: 1px solid var(--vem-rand) !important; border-radius: 0.75rem; padding: 0.9rem 1rem !important;
}
.vt-wrap { background: var(--vem-bg); border: 1px solid var(--vem-rand); border-radius: 0.75rem; padding: 0.35rem 0.4rem; }
/* Minder ruimte tussen de blokken (standaard 1 rem). */
[data-testid="stMainBlockContainer"] [data-testid="stVerticalBlock"] { gap: 0.7rem; }
/* Blokken die alleen opmaak bevatten (<style>) en het onzichtbare inlogcookie (st-key-init) nemen geen ruimte
   in; anders krijgt elk ervan een volle tussenruimte. */
[data-testid="stElementContainer"]:has(> [data-testid="stMarkdown"] style):not(:has(.vem-legenda)) { display: none; }
.st-key-init { position: absolute !important; width: 0; height: 0; overflow: hidden; }

/* ---------- Kop ---------- */
/* Een rustige witte balk met een dunne lijn eronder: groen logoblokje, naam van de app en het bedrijf links,
   week, datum en versie rechts. */
.vem-kop {
    display: flex; justify-content: space-between; align-items: center; gap: 1rem;
    margin: 0 0 0.15rem; padding: 0.15rem 0 0.7rem; border-bottom: 1px solid var(--vem-rand);
}
.vem-merk { display: flex; align-items: center; gap: 0.75rem; min-width: 0; }
.vem-merk .vem-logo-vol { height: 2.1rem; width: auto; flex: none; }
.vem-merk .vem-titel {
    padding-left: 0.75rem; border-left: 1px solid var(--vem-rand); color: var(--vem-zacht);
    font-size: 0.95rem; font-weight: 600;
}
.vem-titel { font-size: 1.2rem; font-weight: 700; letter-spacing: -0.02em; white-space: nowrap; }
.vem-bedrijf { font-size: 0.85rem; color: var(--vem-zacht); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.vem-meta { display: flex; align-items: center; gap: 0.6rem; white-space: nowrap; font-size: 0.85rem; }
.vem-week { font-weight: 600; }
.vem-versie {
    font-size: 0.7rem; font-weight: 500; padding: 0.12rem 0.5rem; border-radius: 1rem;
    background: var(--vem-vlak); color: var(--vem-zacht);
}
@media (max-width: 700px) {
    .vem-bedrijf, .vem-versie, .vem-merk .vem-titel { display: none; }
    .vem-merk .vem-logo-vol { height: 1.85rem; }
    .vem-meta { font-size: 0.8rem; }
}

/* ---------- Zijbalk (breed scherm): logo, pagina's, onderaan week, versie en gebruiker ---------- */
[data-testid="stSidebar"] {
    background: var(--vem-pagina); border-right: 1px solid var(--vem-rand);
    min-width: 232px !important; max-width: 232px !important;
}
[data-testid="stSidebarHeader"], [data-testid="stSidebarCollapseButton"], [data-testid="stSidebarNav"] { display: none !important; }
[data-testid="stSidebarUserContent"] { padding: 1rem 0.85rem 1rem !important; height: 100%; }
[data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"] { gap: 0.4rem; min-height: calc(100vh - 2rem); }
.vem-zijmerk { padding: 0.15rem 0.45rem 0.85rem; margin-bottom: 0.35rem; border-bottom: 1px solid var(--vem-rand); }
.vem-zijmerk .vem-logo-vol { width: 100%; max-width: 190px; height: auto; display: block; }
.vem-zijmerk .vem-titel {
    margin-top: 0.45rem; font-size: 0.72rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase;
    color: var(--vem-oranje);
}
.st-key-vem_zijnav { gap: 2px !important; }
.st-key-vem_zijnav [data-testid="stElementContainer"] { margin: 0 !important; }
.st-key-vem_zijnav [data-testid="stPageLink"] a {
    margin: 0; padding: 0.5rem 0.7rem; border-radius: 0.6rem; gap: 0.65rem; transition: background 0.12s;
}
.st-key-vem_zijnav [data-testid="stPageLink"] a p { font-size: 0.92rem; font-weight: 500; }
.st-key-vem_zijnav [data-testid="stPageLink"] a span[data-testid="stIconMaterial"] { color: var(--vem-zacht); font-size: 1.25rem; }
.st-key-vem_zijnav [data-testid="stPageLink"] a:hover { background: var(--vem-vlak); }
.st-key-vem_zij_actief [data-testid="stPageLink"] a, .st-key-vem_zij_actief [data-testid="stPageLink"] a:hover {
    background: var(--vem-bg); box-shadow: inset 3px 0 0 var(--vem-oranje), var(--vem-schaduw);
}
/* Donker thema: het logo (groene tekst) op een wit plaatje. */
.vem-logo-vol { background: var(--vem-logo-bg); border-radius: 0.4rem; padding: var(--vem-logo-pad); }
.st-key-vem_zij_actief [data-testid="stPageLink"] a p { font-weight: 650; }
.st-key-vem_zij_actief [data-testid="stPageLink"] a span[data-testid="stIconMaterial"] { color: var(--vem-groen); }
/* De voet onderaan de zijbalk. */
[data-testid="stSidebar"] [data-testid="stElementContainer"]:has(.vem-zijvoet) { margin-top: auto; }
.vem-zijvoet { font-size: 0.75rem; line-height: 1.5; color: var(--vem-zacht); padding: 0 0.4rem; }
/* Breed scherm: de navigatie staat in de zijbalk, dus de kop en de navigatie bovenin vallen weg (de week staat
   onderaan de zijbalk). Smal scherm (telefoon, half venster): geen zijbalk, wel de kop en de navigatie bovenin. */
@media (min-width: 900px) {
    /* Altijd open: ook als Streamlit hem heeft ingeklapt (bijv. na een smal venster); een knop om hem weer open
       te zetten is er niet. */
    [data-testid="stSidebar"][aria-expanded="false"] { transform: none !important; margin-left: 0 !important; }
    body:has(.vem-zijmerk) .vem-kop { display: none; }
    body:has(.vem-zijmerk) [data-testid="stElementContainer"]:has(> [data-testid="stMarkdown"] .vem-kop) { display: none; }
    body:has(.vem-zijmerk) [data-testid="stLayoutWrapper"]:has(> .st-key-vem_nav) { display: none; }
    /* Begint de pagina met een filterbalk, dan staan de tuinkeuze en Uitleg rechts op dezelfde regel als de
       filters (periode, weergave …) in plaats van op een eigen regel erboven: de kopbalk wordt een laag
       rechtsboven en die filterbalk houdt rechts ruimte vrij, zodat hij ervoor afbreekt en er nooit onder schuift.
       Begint de pagina met iets anders (bijv. Meer), dan blijft de kopbalk een eigen regel. */
    [data-testid="stMainBlockContainer"] { position: relative; }
    [data-testid="stLayoutWrapper"]:has(> .st-key-vem_kopbalk):has(+ [data-testid="stLayoutWrapper"] > [class*="st-key-filterbalk_"]) {
        position: absolute; top: calc(1rem + 1.45rem); right: 2rem; width: auto; z-index: 5;
    }
    [data-testid="stLayoutWrapper"]:has(> .st-key-vem_kopbalk):has(+ [data-testid="stLayoutWrapper"] > [class*="st-key-filterbalk_"]) > .st-key-vem_kopbalk {
        flex-wrap: nowrap; margin-bottom: 0;
    }
    [data-testid="stLayoutWrapper"]:has(> .st-key-vem_kopbalk) + [data-testid="stLayoutWrapper"] > [class*="st-key-filterbalk_"] {
        padding-right: 20rem;
    }
}
@media (max-width: 899.98px) {
    [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="stExpandSidebarButton"] { display: none !important; }
}

/* ---------- Kopbalk: navigatie, tuinkeuze en Uitleg ---------- */
.st-key-vem_kopbalk { flex-wrap: wrap; row-gap: 0.45rem; column-gap: 0.6rem; margin-bottom: 0.2rem; }
.st-key-vem_tuinkeuze { padding-left: 0; border-left: none; }
[data-testid="stLayoutWrapper"]:has(> .st-key-vem_uitleg) { margin-left: auto; }

/* Navigatie als één spoor: zacht grijsgroen vlak, de huidige pagina wit met een schaduwtje en groene tekst. */
.st-key-vem_nav {
    gap: 2px; flex-wrap: wrap; padding: 3px; border-radius: 0.6rem; background: var(--vem-vlak);
}
/* Streamlit geeft een paginaknop een negatieve marge (−6 px boven en onder); lopen de knoppen op een smal
   scherm door naar een tweede regel, dan schuiven ze daardoor over elkaar. Marge weg. */
.st-key-vem_nav [data-testid="stElementContainer"] { margin: 0 !important; }
.st-key-vem_nav [data-testid="stPageLink"] a {
    margin: 0; padding: 0.28rem 0.75rem; line-height: 1.5; border: none; border-radius: 0.45rem;
    background: transparent; transition: background 0.12s;
}
.st-key-vem_nav [data-testid="stPageLink"] a p { font-size: 0.87rem; font-weight: 500; color: var(--vem-zacht); }
.st-key-vem_nav [data-testid="stPageLink"] a:hover { background: var(--vem-vlak-hover); }
.st-key-vem_nav_actief [data-testid="stPageLink"] a,
.st-key-vem_nav_actief [data-testid="stPageLink"] a:hover { background: var(--vem-gekozen); box-shadow: var(--vem-schaduw); }
.st-key-vem_nav_actief [data-testid="stPageLink"] a p { color: var(--vem-groen) !important; font-weight: 650; }

/* Telefoon: de tuinkeuze als vaste balk onderin het scherm (onder de duim), over de volle breedte; de pagina
   krijgt onderaan ruimte, zodat er niets achter de balk verdwijnt. */
@media (max-width: 700px) {
    .st-key-vem_tuinkeuze {
        position: fixed; left: 0; right: 0; bottom: 0; z-index: 1000; justify-content: center;
        padding: 0.5rem 0.75rem calc(0.5rem + env(safe-area-inset-bottom)); background: var(--vem-bg);
        border-top: 1px solid var(--vem-rand); box-shadow: 0 -4px 16px rgba(16, 24, 20, 0.08);
    }
    .st-key-vem_tuinkeuze > [data-testid="stElementContainer"]:has([data-testid="stButtonGroup"]) {
        flex: 1 1 100% !important; width: 100% !important; max-width: 30rem;
    }
    .st-key-vem_tuinkeuze [data-testid="stButtonGroup"] { width: 100% !important; }
    .st-key-vem_tuinkeuze [data-testid="stButtonGroup"] [role="radiogroup"] { width: 100% !important; flex-wrap: nowrap; }
    .st-key-vem_tuinkeuze button[data-variant="segmented_control"] { flex: 1 1 0; padding-top: 0.45rem; padding-bottom: 0.45rem; }
    .st-key-vem_tuinkeuze [data-testid="stWidgetLabel"] { display: none; }
    [data-testid="stMainBlockContainer"], .block-container { padding-bottom: 5.5rem !important; }
}

/* ---------- Keuzegroepen (st.segmented_control: tuin, weergave, periode, wat registreer je) ---------- */
[data-testid="stButtonGroup"] [role="radiogroup"] {
    gap: 2px; padding: 3px; border-radius: 0.6rem; background: var(--vem-vlak); width: fit-content; max-width: 100%;
    flex-wrap: wrap;
}
button[data-variant="segmented_control"] {
    border: none !important; border-radius: 0.45rem !important; background: transparent !important;
    min-height: 0; padding: 0.24rem 0.75rem; box-shadow: none; transition: background 0.12s;
}
button[data-variant="segmented_control"] p { font-size: 0.87rem; font-weight: 500; color: var(--vem-zacht); }
button[data-variant="segmented_control"]:hover { background: var(--vem-vlak-hover) !important; }
button[data-variant="segmented_control"][aria-checked="true"] {
    background: var(--vem-gekozen) !important; box-shadow: var(--vem-schaduw);
}
button[data-variant="segmented_control"][aria-checked="true"] p { color: var(--vem-groen); font-weight: 650; }
/* Pills (afdelingen, overige filters): gevuld, de gekozen licht groen. */
button[data-variant="pills"] {
    border: 1px solid var(--vem-rand) !important; border-radius: 0.45rem; background: var(--vem-bg) !important;
}
button[data-variant="pills"][aria-checked="true"], button[data-variant="pills"][aria-pressed="true"] {
    background: var(--vem-groen-zacht) !important; color: var(--vem-groen) !important;
}

/* ---------- Knoppen ---------- */
[data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"],
[data-testid="stPopoverButton"], [data-testid="stDownloadButton"] button {
    border: 1px solid var(--vem-rand) !important; background: var(--vem-bg) !important; box-shadow: var(--vem-schaduw);
    font-weight: 500; transition: background 0.12s, border-color 0.12s;
}
[data-testid="stBaseButton-secondary"]:hover, [data-testid="stBaseButton-secondaryFormSubmit"]:hover,
[data-testid="stPopoverButton"]:hover, [data-testid="stDownloadButton"] button:hover {
    background: var(--vem-vlak) !important; border-color: var(--vem-vlak-hover) !important; color: inherit !important;
}
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {
    border: none !important; font-weight: 600; box-shadow: 0 1px 2px rgba(16, 24, 20, 0.18);
}
[data-testid="stBaseButton-primary"]:hover, [data-testid="stBaseButton-primaryFormSubmit"]:hover {
    background: var(--vem-groen-donker) !important;
}
button:disabled { opacity: 0.45; }
/* De knop Uitleg: klein, rechts in de kopbalk. */
.st-key-vem_uitleg [data-testid="stPopover"] button { min-height: 0; padding: 0.2rem 0.65rem; }
.st-key-vem_uitleg [data-testid="stPopover"] button p,
.st-key-vem_uitleg [data-testid="stPopover"] button span { font-size: 0.8rem; }
/* Smal scherm: de knop Uitleg als klein rond ?-icoon rechtsboven in de kop (naast de week), niet op een eigen
   regel tussen de navigatie en de pagina. */
@media (max-width: 899.98px) {
    [data-testid="stMainBlockContainer"] { position: relative; }
    [data-testid="stLayoutWrapper"]:has(> .st-key-vem_uitleg) {
        position: absolute; top: 0.5rem; right: 0.75rem; margin: 0; z-index: 5;
    }
    .st-key-vem_uitleg [data-testid="stPopover"] button {
        width: 2.1rem; height: 2.1rem; min-height: 0; padding: 0 !important; border-radius: 50% !important;
        justify-content: center;
    }
    .st-key-vem_uitleg [data-testid="stPopover"] button [data-testid="stMarkdownContainer"],
    .st-key-vem_uitleg [data-testid="stPopover"] button div[aria-hidden="true"] { display: none; }
    .st-key-vem_uitleg [data-testid="stPopover"] button [data-testid="stIconMaterial"] { font-size: 1.15rem; margin: 0; }
    .vem-meta { margin-right: 2.7rem; }
}
/* ◀ [label ▾] ▶ (ui/filters.bladeraar): het label als vette knop met vaste minimumbreedte. */
[class*="st-key-bladeraar_"] [data-testid="stPopover"] button { min-width: 9rem; font-weight: 600; }
/* ◀ en ▶ altijd op dezelfde regel als het label; past het niet, dan krimpt het label (tekst met …). */
[class*="st-key-bladeraar_"] { flex-wrap: nowrap !important; max-width: 100%; }
[class*="st-key-bladeraar_"] > [data-testid="stLayoutWrapper"]:has([data-testid="stPopover"]),
[class*="st-key-bladeraar_"] > [data-testid="stElementContainer"]:has([data-testid="stPopover"]) {
    flex: 0 1 auto !important; min-width: 0 !important;
}
[class*="st-key-bladeraar_"] [data-testid="stPopover"], [class*="st-key-bladeraar_"] [data-testid="stPopover"] button {
    min-width: 0 !important; max-width: 100%;
}
@media (max-width: 700px) {
    [class*="st-key-bladeraar_"] > [data-testid="stLayoutWrapper"]:has([data-testid="stPopover"]),
    [class*="st-key-bladeraar_"] > [data-testid="stElementContainer"]:has([data-testid="stPopover"]) {
        flex: 1 1 auto !important; width: auto !important;
    }
    [class*="st-key-bladeraar_"] [data-testid="stPopover"], [class*="st-key-bladeraar_"] [data-testid="stPopover"] button {
        width: 100% !important;
    }
}

/* ---------- Velden en labels ---------- */
/* Keuze- en invoervelden op het hoofdscherm niet breder dan nodig: op een breed scherm oogt een smal veld
   strakker. De zijbalk en popups houden hun eigen breedte. */
[data-testid="stMain"] [data-testid="stSelectbox"],
[data-testid="stMain"] [data-testid="stMultiSelect"],
[data-testid="stMain"] [data-testid="stDateInput"],
[data-testid="stMain"] [data-testid="stTextInput"],
[data-testid="stMain"] [data-testid="stNumberInput"],
[data-testid="stMain"] [data-testid="stSelectSlider"] { max-width: 360px; }
[data-testid="stMain"] [data-testid="stTextArea"] { max-width: 720px; }
[data-testid="stWidgetLabel"] p { font-size: 0.8rem; font-weight: 500; color: var(--vem-zacht); }
/* Een veld licht op met een groene rand als je erin typt. */
[data-baseweb="input"]:focus-within, [data-baseweb="select"] > div:focus-within, [data-baseweb="textarea"]:focus-within {
    box-shadow: 0 0 0 2px var(--vem-groen-zacht); border-color: var(--vem-groen) !important;
}

/* ---------- Kaders: openklapmenu's, popovers, tabellen ---------- */
[data-testid="stExpander"] details {
    border: 1px solid var(--vem-rand); border-radius: 0.75rem; background: var(--vem-bg);
}
[data-testid="stExpander"] summary { padding-top: 0.6rem; padding-bottom: 0.6rem; }
[data-testid="stExpander"] summary p { font-weight: 600; font-size: 0.93rem; }
[data-testid="stExpander"] summary:hover { background: var(--vem-vlak); border-radius: 0.75rem; }
[data-testid="stPopoverBody"] { border-radius: 0.75rem; border: 1px solid var(--vem-rand);
    box-shadow: 0 8px 24px rgba(16, 24, 20, 0.12); }
[data-testid="stDataFrame"], [data-testid="stDataFrameResizable"] { border-radius: 0.75rem; }
/* Kaders van st.container(border=True) als kaart. */
[data-testid="stVerticalBlockBorderWrapper"][data-test-scroll-behavior], [class*="st-key-"][data-testid="stVerticalBlock"][style*="border"] {
    border-radius: 0.75rem;
}
/* Tabbladen (st.tabs, bijv. Wijzigen): onderstreept, de gekozen groen. */
[data-testid="stTabs"] [role="tab"] p { font-weight: 500; }
[data-testid="stTabs"] [role="tab"][aria-selected="true"] p { color: var(--vem-groen); font-weight: 650; }
/* Meldingen (st.info, st.success …) zonder zware rand, wat compacter. */
[data-testid="stAlert"] > div { border-radius: 0.6rem; padding-top: 0.6rem; padding-bottom: 0.6rem; }

/* ---------- Paginaopbouw (ui/layout.py) ---------- */
.vem-sectie { font-size: 1.12rem; font-weight: 700; letter-spacing: -0.02em; margin: 0.6rem 0 0; }
.vem-sectie span { font-weight: 400; color: var(--vem-zacht); }
/* Schermnummer voor feedback ("2.3"): klein en grijs vóór het kopje. */
.vem-sectie .vem-nr { font-weight: 500; font-size: 0.75rem; color: var(--vem-zacht); margin-right: 0.45rem; }
[class*="st-key-filterbalk_"] { flex-wrap: wrap; row-gap: 0.5rem; margin-bottom: 0.1rem; }
[class*="st-key-filterbalk_"] [data-testid="stCheckbox"] { padding-bottom: 0.45rem; }
/* Stek, "Hele week invullen": alle velden op één regel, dicht op elkaar. */
.st-key-stek_week_rij { flex-wrap: wrap; gap: 0.5rem !important; }

/* ---------- Kengetallen (tegels) ---------- */
/* Compacte tegels naast elkaar, elk zo breed als de inhoud (nooit een waarde over twee regels), die
   doorlopen naar een volgende regel. */
.vem-kg-titel {
    font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em;
    color: var(--vem-zacht); margin: 0.8rem 0 0.35rem;
}
/* Als kleine kaarten: wit met een dunne rand, het label klein bovenaan, de waarde vet. */
.vem-kg { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.25rem; }
.vem-kg-tegel {
    flex: 0 0 auto; min-width: 5.5rem; border: 1px solid var(--vem-rand); border-radius: 0.55rem;
    background: var(--vem-bg); padding: 0.3rem 0.6rem 0.35rem; line-height: 1.2;
}
.vem-kg-label, .vem-kg-waarde, .vem-kg-delta { white-space: nowrap; }
.vem-kg-label { font-size: 0.7rem; font-weight: 500; color: var(--vem-zacht); }
.vem-kg-label abbr { text-decoration: none; cursor: help; opacity: 0.8; margin-left: 0.2rem; }
.vem-kg-waarde { font-size: 0.98rem; font-weight: 650; margin-top: 0.05rem; letter-spacing: -0.01em; }
.vem-kg-delta { font-size: 0.66rem; color: var(--vem-zacht); margin-top: 0.05rem; }

/* ---------- Vergelijkingstabel (ui/vergelijkingstabel.py) ---------- */
/* Strak: alleen horizontale lijnen, geen zebra, waarden nooit afgebroken. Streamlit zet om elke cel van een
   markdown-tabel een rand; die gaat eraf. Past de tabel niet (smal scherm), dan schuift hij zijwaarts met de
   eerste kolom vast. */
.vt-wrap { max-width: 900px; margin: 0.25rem 0 0.4rem; }
.vt-wrap.vt-breed { max-width: none; overflow-x: auto; }
/* Smal scherm: de tabel schuift zijwaarts in zijn eigen kader; de vaste kopregel rekent dan vanaf dat kader. */
@media (max-width: 900px) { .vt-wrap { overflow-x: auto; } }
table.vt {
    width: 100%; border-collapse: separate; border-spacing: 0; table-layout: auto;
    font-variant-numeric: tabular-nums; border: none;
}
table.vt col.vt-col-onderwerp { width: 170px; }
table.vt th, table.vt td {
    padding: 4px 10px; text-align: right; vertical-align: top; white-space: nowrap;
    border: none; border-bottom: 1px solid var(--vem-rand);
}
table.vt thead th {
    position: sticky; top: 0; z-index: 2; background: var(--vt-bg);
    font-size: 11.5px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; color: var(--vem-zacht);
    padding-top: 7px; padding-bottom: 6px; border-bottom: 1px solid var(--vem-rand);
}
table.vt th:first-child, table.vt td:first-child {
    text-align: left; position: sticky; left: 0; z-index: 1; background: var(--vt-bg);
}
table.vt thead th:first-child { z-index: 3; }
table.vt td.vt-onderwerp { font-size: 14px; cursor: help; padding-top: 5px; white-space: normal; min-width: 130px; }
table.vt td.vt-onderwerp .vt-i { font-size: 10.5px; opacity: 0.45; margin-left: 4px; }
table.vt .vt-waarde { font-size: 13.5px; font-weight: 500; line-height: 1.35; }
table.vt .vt-toelichting { font-size: 11.5px; line-height: 1.15; opacity: 0.6; }
table.vt .vt-vergelijk { font-size: 11.5px; line-height: 1.15; margin-top: 1px; }
table.vt .vt-vergelijk-tekst { opacity: 0.6; }
table.vt .vt-waarschuwing { font-size: 11.5px; margin-left: 4px; color: #c98a00; font-weight: 400; }
table.vt sup.vt-noot-teken { font-size: 10px; font-weight: 400; opacity: 0.55; margin-left: 3px; }
table.vt th.vt-totaal, table.vt td.vt-totaal {
    border-left: 1px solid var(--vem-rand);
    background-image: linear-gradient(rgba(128, 128, 128, 0.05), rgba(128, 128, 128, 0.05));
}
table.vt td.vt-beste { background-image: linear-gradient(rgba(46, 160, 67, 0.13), rgba(46, 160, 67, 0.13)); }
/* Groepkop (Bezetting & productie, Klimaat …): een eigen balk met ruimte erboven, zodat de onderwerpen
   duidelijk gescheiden zijn. De eerste groep direct onder de kop zonder extra ruimte. */
table.vt tr.vt-groep td {
    padding: 7px 10px 6px; font-size: 12px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase;
    color: var(--vem-groen); background: var(--vem-groen-zacht);
    border-top: 18px solid var(--vt-bg); border-bottom: none;
}
table.vt tbody tr.vt-groep:first-child td { border-top-width: 0; }
.vt-beter { color: #2e9a44; }
.vt-slechter { color: #d64541; }
.vt-neutraal, .vt-leeg { opacity: 0.55; }
.vt-noot { font-size: 12px; opacity: 0.7; margin: 2px 0 6px; }
"""


def laad():
    """Zet de CSS op de pagina, met de kleuren van het actieve thema (licht of donker)."""
    thema = getattr(getattr(st.context, "theme", None), "type", None) or "light"
    palet = PALET.get(thema, PALET["light"])
    variabelen = "".join(f"--vem-{naam}: {waarde}; " for naam, waarde in palet.items())
    st.markdown(f"<style>:root {{ --vt-bg: {palet['bg']}; {variabelen}}}{CSS}</style>", unsafe_allow_html=True)
