# Changelog

Alle belangrijke wijzigingen aan de Teeltregistratie-app worden hier bijgehouden,
inclusief de reden erachter. Nieuwste wijzigingen staan bovenaan.

## [2.8.0] - 2026-10-08

### Toegevoegd
- **Pagina Opzoeken**: een teelt (alle vakken uit één plantweek) of één vak met alle
  informatie die er is. Kies de teelt met ◀ ▶ (dezelfde keuze als Teeltvergelijking) en
  een vak, of zoek op een teeltcode of vaknummer. Bij een teelt een samenvatting, bij één vak
  alles uit de vakpopup; de vakken van de teelt staan er altijd bij. Daaronder elke bron in
  een openklapmenu: oogst, Florgib en lengtes, opmerkingen, stek, watergift, gietbeurten,
  EC/pH, klimaat, warmte en gas, het verloop van de prognose, behandelingen, teelthistorie
  en wijzigingen, en alles in één Excel-bestand. Watergift, klimaat en energie per vak van
  planten tot oogst. In de vakpopup gaat de knop *Alles over dit vak* naar deze pagina.

### Gewijzigd
- **Planning en Teeltoverzicht samengevoegd** tot één pagina Teeltoverzicht, met de
  **tijdlijn** als hoofdweergave: per vak één regel met de afgeronde teelten (grijs), de
  lopende teelt tot vandaag in de statuskleur van de vakkenmatrix en daarna licht tot de
  prognose-oogst, bevestigde teelten, concepten en overlap (rode stippelrand). Per afdeling
  een kopregel met het stookadvies, bovenaan het weeknummer en het aantal vakken dat per
  week (bij 6 mnd / 1 jaar per 2 of 4 weken) geoogst wordt. De vakkenmatrix blijft
  beschikbaar via Weergave › Vakken nu. Waarom: de status van een vak en wat er daarna
  gepland staat hoorden bij elkaar, maar stonden op twee pagina's.
- **Concepten bewerken in de tijdlijn**: klik op een concept om het te verschuiven, te
  starten als teelt of te verwijderen; klik op een lege plek in een vakregel om daar een
  concept te plannen. Met een waarschuwing als de planting overlapt met de vorige of de
  volgende ronde.
- De concepttabel, de jaarplanning, het overzicht per plantweek en de vooruitblik staan in
  openklapmenu's onder de tijdlijn; het vakkenregister staat daaronder.
- Vervallen: de strokenplanning (Gantt) en "Eén vak handmatig plannen" (de tijdlijn doet
  beide). Het adres /planning bestaat niet meer.
- **Zijbalk 330 px breed** (was 300): de knoppen Florgib · Oogst · Opmerking · Wijzigen
  passen op één regel en de invoervelden hebben meer ruimte.
- **Geen paginatitel meer** onder de navigatie: de gevulde knop laat al zien waar je bent. De
  knop Uitleg is kleiner en staat rechts op de regel van de tuinkeuze; dat scheelt een regel.
- Excel-export: tekens die Excel niet toestaat in een bladnaam (zoals /) worden een streepje.
- **Strakkere knoppen**: overal een kleine ronding van 0,2 rem in plaats van ronde hoeken en
  pilvormen (thema in `.streamlit/config.toml`; navigatiebalk, kop, afdelingsknoppen,
  vakblokken en tegels volgen dezelfde ronding).

### Gecorrigeerd
- Weeknummers bij de wintertijd: in de strokenplanning stond week 43 twee keer en
  ontbrak week 44 (zondag + 24 uur viel op de 25-uursdag nog op zondag).

## [2.7.1] - 2026-10-07

### Gecorrigeerd
- **Watergift na het op nul zetten van de tellers.** Op 06-10-26 om 10:48 zijn
  de watertellers van tuin 3 gereset; de oude stand kwam 26 seconden later nog
  één keer terug. Die terugsprong telde als gift: 55–599 l/m² per vak in plaats
  van 0–13. Een sprong terug naar de stand van vóór een reset (binnen een uur)
  en een stap van meer dan 50 l/m² tellen nu niet meer, ook niet als gietbeurt.
  Een dag met alleen een reset krijgt 0,0, zodat een eerder foute waarde wordt
  overschreven.

## [2.7.0] - 2026-10-01

### Gewijzigd
- **Teeltcode met de tuin erin**: jaar + plantweek + tuin + vak (7 cijfers),
  bijv. 2634301 = 2026, week 34, tuin 3, vak 1. De codes van tuin 1 en tuin 3
  zijn daardoor niet meer gelijk (262701 bestond in beide tuinen).
- Alle bestaande codes omgezet met `herstel_teeltcodes.py` (386 vakken, het
  prognoselogboek volgt mee); alleen het tuincijfer komt ertussen. De
  teelthistorie heeft geen teeltcodes en blijft zoals hij is.

## [2.6.3] - 2026-10-01

### Toegevoegd
- `importeer_florgib_overview.py` vult voor afgeronde vakken van tuin 3 ook
  de **oogstlengte** en het **oogstgewicht** uit het blad Plantingen, alleen
  waar die in de app nog leeg zijn. Gewicht = het gemiddelde van "Gewicht
  2-3" en "Gewicht 3-4" (rijpheid 2-4), of het enige gewicht dat er is.
  Op productie gedraaid: 10 vakken een gewicht (wk 24 800 g, wk 25 775 g,
  wk 26 650 g, wk 27 700 g); oogstlengtes stonden er al allemaal.

## [2.6.2] - 2026-10-01

### Toegevoegd
- `importeer_florgib_overview.py` vult nu ook de **lengte bij de Florgib**
  met de knoplengte uit het blad Plantingen van tuin 3 (één waarde per
  plantweek van het lopende jaar), voor vakken met een Florgib en zonder
  lengte in de app. Gecontroleerd: waar de app al een lengte had (wk 27–31)
  is die gelijk. Op productie gedraaid: 47 vakken (wk 12–27 '26).

## [2.6.1] - 2026-10-01

### Toegevoegd
- `importeer_florgib_overview.py`: vult de Florgib-datum van vakken zonder
  Florgib met de eerste "Fg" uit het blad Overview van de klimaatregistratie
  (tuin 1 en 3), tussen planten en oogst. Overschrijft nooit een registratie
  in de app; elke wijziging staat in het logboek. Op productie gedraaid:
  232 vakken bijgewerkt (tuin 1: 17, tuin 3: 215). De lengte bij de Florgib
  staat niet in Overview en blijft leeg.

## [2.6.0] - 2026-10-01

### Toegevoegd
- **Meer › Ruwe data**: de onderliggende tabellen om iets op te zoeken (vakken,
  emmers, klimaat, watergift, gietbeurten, EC/pH, warmte, gas, stek,
  opmerkingen, concept- en jaarplanning, prognoselogboek, teelthistorie en
  vakgegevens). Alleen lezen, voor de tuin bovenaan, met filters op periode,
  vak en een woord (zoekt in alle kolommen). Datums als dd-mm-yy, tijden in
  Nederlandse tijd. Export naar Excel en CSV. Gebruikers, instellingen en het
  logboek staan er bewust niet in.

## [2.5.1] - 2026-09-30

### Gewijzigd
- Teeltvergelijking: **Stelen per m²** vervangen door totalen: **Geplant**
  (planten, onder Vakken) en **Geoogste stelen** (emmers × 100, anders
  geplant × (1 − uitval); ⏳ = met de emmers tot nu van lopende vakken).
  In de vakkentabel de kolommen Planten en Geoogst (st).

 - 2026-09-30

Eén UI-standaard voor de hele app (docs/ui-standaard.md): overal dezelfde
paginaopbouw, hetzelfde element per soort keuze en uitleg op één manier.

### Gewijzigd
- **Weken lopen overal van zondag t/m zaterdag** (kop, Tuin vergelijking,
  Watergift, Opmerkingen, Gantt, vooruitblik). Teeltcodes en plantweken
  blijven de ISO-week van de plantdatum.
- Elke pagina: titel met een knop **Uitleg** (vaste kopjes: wat zie je, hoe
  lees je het, waar komen de getallen vandaan, wat betekenen de kleuren).
  "Hoe lees ik dit?" (Planning) en het tabblad "Hoe dit werkt" (Meer) vervallen.
- **Tuin** alleen nog bovenaan. Planning, Stek en Meer werken per tuin (Beide
  kan daar niet), Tuin vergelijking altijd over beide tuinen. Bij Beide vraagt
  de zijbalk "Registreren in".
- **Periode** overal als knoppengroep + ◀ [label ▾] ▶ met een sprongkeuze
  (Tuin vergelijking, Watergift, Opmerkingen, plantperiode in het register);
  teelt en pootweek op dezelfde manier (Teeltvergelijking, Stek). Geen
  schuifjes of datumbereiken meer om te filteren.
- Afdeling als aan/uit-labels, gedeeld tussen Teeltoverzicht en Watergift;
  ras, categorie, type en gebruiker als labels of keuzelijst; zoeken altijd
  als laatste.
- Filterkeuzes blijven bewaard als je van pagina wisselt.
- **Eén vakpopup** vanuit elke pagina, voor lopende en afgeronde vakken, met
  de vergelijking met vorig jaar als openklapmenu. De aparte
  watergiftgrafiek in de popup vervalt (staafjes op de tijdlijn en de tabel
  Watergift per dag blijven).
- Teeltvergelijking: de eigen tuin- en vak-keuzelijst vervallen; een vak
  licht op door erop te klikken.
- Tuin vergelijking: "Watergift per vak" vervalt; geplante vakken, watergift
  en opmerkingen zijn links naar de pagina met het juiste filter.
- Zichtbare legenda onder de matrix (Teeltoverzicht, Watergift) en de Gantt.
- Zijbalk: "Wat wil je doen?" als knoppengroep op één regel. Stek: "uitval" heet
  stekuitval.

### Toegevoegd
- Excel-export van het vakkenregister en van de opmerkingen.
- Register: plantperiode per week, maand, kwartaal of jaar.
- Logboek: zoeken in de omschrijving.

## [2.4.2] - 2026-09-30

### Gewijzigd
- Vakkenregister › Afgerond: kolom Stelen/m² vervangen door **Geplant** en
  **Geoogst (stelen)**, direct na Fase 2 en vóór Uitval (%).
- Vakpopup, tijdlijn: labels vallen niet meer buiten beeld; **watergift per
  dag** als staafjes óp de tijdlijn (hoogte naar de gift), labels in twee
  rijen eronder.

## [2.4.1] - 2026-09-30

### Gecorrigeerd
- Watergift: teeltkleur per teeltronde (tuin 3 vanaf vak 2, tuin 1 vanaf
  vak 1; `RONDE_STARTVAK` in config.py): één rustige kleur per ronde (groen,
  lila, grijsblauw), daarbinnen per teelt afwisselend licht en donker.
- Watergift: kruis bij het aanwijzen weer weg (maakte de pagina traag).
- Watergift: gift in één vaste blauwe kleur met witte tekst (geen kleurschaal
  meer); oranje alleen nog op de laatste oogstdag (oogstdatum, of de laatste
  emmerdag zolang het vak niet is afgerond).

### Toegevoegd
- Watergift: verwachte Florgib (teeltmodel) als open paarse ring, zolang er
  nog geen Florgib geregistreerd is.
- **EC, pH en flow per gietbeurt**, gerekend zoals Priva (gemiddelde over de
  beurt; gecontroleerd tegen het kraanoverzicht van 29-09): nieuwe tabel
  `watergift_beurt`, EC/pH per vak-dag in `watergift_dag` en per dag
  (`ec_gift`, `ph_gift`) in `water_kwaliteit_dag`, alle gewogen naar de liters.
  Matrix: EC/pH-regels en tooltips uit de giften; dagpopup met elke gietbeurt.
- Tabellen ronden getallen nu af in plaats van af te kappen (21,89 → 21,9).

### Gecorrigeerd
- Watergift: een gietbeurt begint bij de eerste wijziging van de meterstand,
  niet bij de vorige (tot 12 uur oude) stand; ook de dag van de liters volgt
  daaruit.

## [2.4.0] - 2026-09-30

### Toegevoegd
- **Pagina Watergift**: matrix vak × dag met de watergift (l/m²), EC
  uitgangswater, EC en pH (rood buiten de band EC 1,0–2,0 / pH 4,8–6,0),
  teeltkleur per plantweek, plantdag, Florgib, oogst (verwacht: licht oranje),
  concept-planning t/m volgende week, weken zo–za, vooruitkijken t/m de
  verwachte oogst van de laatste lopende of bevestigde teelt, kruis bij het
  aanwijzen, klik op vak (vakpopup) of dag (dagpopup), Download Excel.
- **EC van het uitgangswater** (voorregeling) uit Priva, kolom `ec_aanvoer`.
- Vakpopup: watergift per dag met gietbeurten en EC/pH.

## [2.3.0] - 2026-09-30

### Toegevoegd
- **EC en pH van de gift** uit Priva (watersysteem 1, per tuin), in hetzelfde
  verzoek als de watergift: daggemiddelde (tijdgewogen), min/max, ingestelde EC
  en actief recept. Nieuwe tabel `water_kwaliteit_dag`; dekking onder Meer ›
  Data importeren. Priva bewaart 5 dagen, dus de historie begint nu.
- Aantal **gietbeurten** per vak-dag (kolom `beurten` in `watergift_dag`).
- Lege tabellen `middel` en `behandeling` en de adapter
  `integrations/behandelingen/` voor gewasbescherming en biologie (later).

## [2.2.0] - 2026-09-30

### Toegevoegd
- **Versienummer** rechtsboven in de kop (`APP_VERSIE` in `config.py`). Ophogen
  bij elke wijziging op main: derde getal bij een correctie, tweede bij iets
  nieuws, eerste bij een grote omzetting.
- **Nieuwe kop** "Teeltregistratie · Van Egmond Matricaria" met week, datum en
  versie, en daaronder een eigen navigatiebalk met een knop per pagina (de
  huidige gevuld groen). De losse paginatitel is weg; de uitleg staat als ⓘ.

### Gewijzigd
- Wijzigen of verwijderen: kiezen in de volgorde **week → vak → jaar**; weken in
  de tijd (recentste onderaan).
- Teeltvergelijking: kiezen met **tuin → week → vak → jaar**, in één compacte rij.
- Keuzerijen (Teeltvergelijking, Tuin vergelijking, vakkenregister, Opmerkingen)
  links uitgelijnd met vaste breedtes in plaats van over het hele scherm.
- Vakkenregister › Afgerond: **laatst geoogst bovenaan**.

## [2.1.0] - 2026-09-30

### Toegevoegd
- **Opmerkingen per vak** (zijbalk › Opmerking), terug te zien in de vakpopup,
  op de pagina Opmerkingen (filters op tuin, teelt, vak, periode, categorie,
  tekst), bij de gekozen teelt (Teeltvergelijking) en periode (Tuin vergelijking).
- Wijzigen of verwijderen per onderdeel: startdatum en planten (met ras),
  Florgib, oogst, opmerkingen.

## [2.0.0] - 2026-09-29

### Gewijzigd
- **Herindeling**: losse pagina's (Planning, Stek, Teeltoverzicht,
  Teeltvergelijking, Tuin vergelijking, Meer) met eigen adres; Teeltoverzicht =
  vakkenmatrix + vakkenregister; Planning met één concepttabel.
- **Prognoselogboek** en Meer › Prognosekwaliteit.

## [Niet uitgebracht] - 2026-08-28

### Toegevoegd
- Bij "Nieuwe teelt registreren" wordt het **aantal stelen automatisch
  vooringevuld** op basis van het vaknummer (uitgangspunt ± 60 stelen per meter):
  vak 1 → 34000, vak 2-18 en 21-38 → 32688, vak 19 en 20 → 15436, vak 39 → 31780.
  Het vaknummer staat daarvoor nu buiten het formulier; de waarde blijft
  handmatig aanpasbaar.
- Titel van het browsertabblad is nu "VEM teeltregistratie" (met 🌱-icoon) in
  plaats van "Streamlit", via `st.set_page_config`.
- Bij "Oogst registeren" → tabblad 🪣 Uitval zijn nu **ook afgeronde teelten
  kiesbaar**, zodat je het aantal geoogste emmers achteraf nog kunt corrigeren.
  Elk oogstmoment heeft een 💾-knop om het aantal aan te passen (naast de
  bestaande 🗑️ om het te verwijderen). Nieuwe functie
  `wijzig_oogstregistratie()` in `database.py`. *Waarom:* correcties op de
  emmer-telling waren na het afronden van een teelt niet meer mogelijk.
- **Inlogscherm** (`streamlit-authenticator`). De app toont eerst een
  inlogformulier; pas na inloggen zijn de registratie-functies en het overzicht
  zichtbaar. In de zijbalk staat wie er is ingelogd en een "Uitloggen"-knop.
  *Waarom:* de app draait nu tegen een gedeelde database in de cloud en moet
  niet voor iedereen open staan.
- Nieuwe tabel `gebruikers` in de database (`username`, `naam`,
  `wachtwoord_hash`, `email`). Wachtwoorden worden als bcrypt-hash opgeslagen,
  nooit in platte tekst.
- Hulpscript `beheer_gebruikers.py` om gebruikers toe te voegen, te tonen of te
  verwijderen (`python beheer_gebruikers.py toevoegen <naam> "<Volledige naam>"`).
  Het wachtwoord wordt interactief gevraagd en meteen gehasht.
- Omgevingsvariabele `AUTH_COOKIE_KEY` waarmee het inlog-cookie wordt
  ondertekend. Ontbreekt hij, dan gebruikt de app een tijdelijke sleutel per
  serverstart (met waarschuwing).

### Gewijzigd
- Tabblad 📏 Oogstgewicht en lengte toont nog alleen teelten die **niet zijn
  afgerond** bij de uitval (was: alle teelten). *Waarom:* lengte/gewicht/rijpheid
  vul je in tijdens de teelt; na het afronden hoort die lijst leeg te zijn.
- **Databaseverbinding wordt hergebruikt** in plaats van bij elke Streamlit-rerun
  opnieuw opgezet. `database.py` gebruikt nu één proces-brede
  `ThreadedConnectionPool`; `get_connection()` is een context manager
  (`with get_connection() as conn:`) die een verbinding uit de pool leent,
  teruggeeft, en een door de server gesloten verbinding automatisch vervangt.
  Alle functienamen en het gedrag blijven gelijk. *Waarom:* elke rerun deed
  meerdere volledige connect-handshakes (TCP + TLS + auth) naar Supabase; dat
  was merkbaar traag.
- `init_db()` draait nog maar één keer per serverstart (via `@st.cache_resource`
  in `app.py`) in plaats van bij elke rerun.
- De opslag is overgezet van een lokaal SQLite-bestand (`teeltdata.db`) naar
  PostgreSQL (Supabase). `database.py` gebruikt nu `psycopg2` in plaats van
  `sqlite3`; alle functienamen en het gedrag zijn hetzelfde gebleven, dus
  `app.py` verandert niet. *Waarom:* een gedeelde database in de cloud zodat de
  registratie vanaf meerdere apparaten werkt en niet aan één machine vastzit.
- De connectiegegevens komen uit de omgevingsvariabele `DATABASE_URL` (de
  PostgreSQL-connectiestring van het Supabase-project). Er staat niets van de
  connectiestring in de code. *Waarom:* wachtwoorden en host horen niet in
  versiebeheer.
- `id`-kolommen zijn nu `SERIAL` (PostgreSQL) i.p.v. `INTEGER PRIMARY KEY
  AUTOINCREMENT`; nieuwe rijen worden ingevoegd met `RETURNING id`. Datums
  blijven als ISO-tekst (`YYYY-MM-DD`) opgeslagen, net als voorheen.
- `psycopg2-binary` toegevoegd aan de requirements.
- Voor lokaal testen leest `database.py` bij het opstarten een `.env`-bestand in
  (met `DATABASE_URL`). `.env` staat in `.gitignore`; `.env.example` laat het
  formaat zien. *Waarom:* de connectiestring lokaal kunnen zetten zonder hem in
  versiebeheer of in de code te krijgen.

## [Niet uitgebracht] - 2026-08-27

### Gewijzigd
- Menu-opties hernoemd: "1. Nieuw teeltvak(ken) starten" → "1. Nieuwe teelt
  registreren", "2. Lengte halverwege toevoegen" → "2. Florgib lengte
  registreren", "3. Eindstand / Oogst toevoegen" → "3. Oogst registeren",
  "4. Registratie wijzigen / verwijderen" → "4. Registratie wijzigen of
  verwijderen". De bijbehorende sidebar-koppen en het "Hoe dit werkt"-blok zijn
  meegenomen. *Waarom:* de nieuwe namen sluiten aan bij hoe er in de praktijk
  over de stappen gesproken wordt (o.a. "Florgib lengte" i.p.v. "halverwege").
- Datums worden overal weergegeven als dd-mm-jj (bijv. `27-08-26`), inclusief de
  overzichtstabel op het hoofdscherm en alle bevestigingsmeldingen. De
  datumvelden in de zijbalk tonen `DD-MM-YYYY`. In de database blijven datums in
  ISO-formaat (`YYYY-MM-DD`) opgeslagen zodat sorteren, weeknummer- en
  teeltduurberekening blijven werken; alleen de weergave verandert. *Waarom:*
  dd-mm-jj is de gewenste leesbare notatie.
- Alle getallen worden zonder decimalen genoteerd (oogstgewicht in kg, aantal
  emmers, uitvalpercentage), behalve de lengtes (Florgib lengte en eindlengte),
  die één decimaal houden. *Waarom:* de overige waarden worden in de praktijk
  als hele getallen bijgehouden.
- Het invulveld "Label (optioneel)" bij het registreren van een nieuwe teelt is
  verwijderd; teeltvakken worden aangeduid met hun vaknummer. *Waarom:* het veld
  werd niet gebruikt naast het vaknummer.
- Kolomvolgorde van de overzichtstabel: Startdatum, Teeltvak, Datum Halverwege,
  Lengte Half (cm), Oogstdatum, Teeltduur (dagen), Oogstlengte (cm),
  Oogstgewicht (gram), Rijpheid, Uitval (%), Aantal Planten, Aantal Emmers,
  Aantal Stelen, Code.
- De rijen worden in de database gesorteerd op teeltcode, van laag naar hoog.
  De losse sortering in de app is verwijderd omdat die op de weergegeven
  dd-mm-jj-tekst sorteerde en dus niet meer chronologisch was.
- "Lengte Einde (cm)" hernoemd naar "Oogstlengte (cm)" en "Gewicht (kg)" naar
  "Oogstgewicht (gram)". Het oogstgewicht wordt voortaan in grammen ingevoerd en
  weergegeven; bestaande waarden stonden al in grammen en zijn ongewijzigd
  gelaten. *Waarom:* het gewicht wordt in de praktijk in grammen bijgehouden.
- Het uitvalpercentage wordt weergegeven met 2 decimalen (zowel in de
  overzichtstabel als bij het registreren van emmers). *Waarom:* bij grote
  aantallen planten is één decimaal te grof om verschillen te zien.

## [Niet uitgebracht] - 2026-08-26

### Gewijzigd
- Menu-opties "3. Eindstand / Oogst toevoegen" en "5. Emmers oogst
  registreren" samengevoegd tot één actie "3. Eindstand / Oogst toevoegen".
  Emmers registreren en de eindstand (lengte/gewicht/rijpheid) invullen
  staan nu onder elkaar in dezelfde sidebar-sectie, maar blijven twee losse
  formulieren. *Waarom:* het waren twee aparte, vergelijkbare menu-items;
  door emmers en eindstand los van elkaar te houden kun je emmers zo vaak
  registreren als nodig zonder steeds ook lengte, gewicht en rijpheid te
  moeten invullen.
- Teelt-keuzelijsten (dropdowns/multiselects) tonen nu alleen nog vak,
  teelt-ID en plantweek (bijv. "Vak 4 - Teelt 12 - week 9"), in plaats van
  ook code, startdatum en status. *Waarom:* de lijsten bevatten te veel
  informatie om snel de juiste teelt te kunnen kiezen.

## [e88e3c1] - 2026-08-26

### Toegevoegd
- **Vaknummer + unieke teeltcode**: elk teeltvak heeft nu een vaknummer (1-39) in
  plaats van een vrije naam. Bij het starten van een teelt wordt automatisch een
  unieke code gegenereerd (jaar + plantweek + vaknummer, bijv. `260904`).
  *Waarom:* voorheen kon je teeltvakken alleen los van elkaar herkennen aan hun
  naam; de code maakt teelten in overzichten en selecties eenduidig herleidbaar
  naar wanneer en waar ze gestart zijn.
- **Aantal geplante planten** per teelt vastleggen bij het starten of wijzigen
  van een registratie. *Waarom:* nodig als basis om later het uitvalpercentage
  te kunnen berekenen.
- **Emmers oogst registreren** (nieuwe actie "5. Emmers oogst registreren"):
  meerdere oogstmomenten per teelt vastleggen in aantal emmers (100 stelen per
  emmer), met overzicht van totaal geoogste emmers/stelen en het
  uitvalpercentage t.o.v. het aantal geplante planten. Oogstmomenten zijn ook
  individueel te verwijderen. *Waarom:* de oogst gebeurt in meerdere rondes per
  teeltvak; één vast oogstmoment per teelt was niet genoeg om dat te
  registreren.
- Startformulier voor nieuwe teeltvakken werkt nu met een tabel
  (vaknummer, optioneel label, aantal planten) in plaats van een vrij tekstveld
  met komma-gescheiden namen. *Waarom:* sluit aan bij het nieuwe vaknummer- en
  plantenaantal-systeem en voorkomt typefouten in vaknamen.
- Overzichtstabel op het hoofdscherm toont nu ook code, aantal planten, totaal
  geoogste emmers/stelen en uitvalpercentage per teelt.

### Gewijzigd
- `start_nieuwe_teelt` en `update_teelt_volledig` accepteren vaknummer en
  aantal planten, en genereren/bewaren de teeltcode.
- Bestaande databases migreren automatisch: nieuwe kolommen
  (`aantal_planten`, `code`, `vaknummer`) en de `oogstregistraties`-tabel
  worden bij opstarten toegevoegd zonder bestaande data te verliezen.

## [0fa458f] - eerdere wijziging
### Toegevoegd
- Rijpheidsstadium toegevoegd aan oogstregistratie.

## [3194188] - Eerste lokale commit
- Initiële versie van de Teeltregistratie-app (start, halverwege- en
  eindregistratie per teeltvak).
