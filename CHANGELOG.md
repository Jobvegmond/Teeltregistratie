# Changelog

Alle belangrijke wijzigingen aan de Teeltregistratie-app worden hier bijgehouden,
inclusief de reden erachter. Nieuwste wijzigingen staan bovenaan.

## [2.22.1] - 2026-10-28

### Gewijzigd
- `pats_import.py`: staan er van een tuin nog geen PATS-tellingen in de database, dan haalt het de eerste keer
  60 dagen op in plaats van 14 (zo staat online meteen een flink stuk historie).

## [2.22.0] - 2026-10-27

### Toegevoegd
- **Insectentellingen van PATS in het Overzicht** (weergave *Bespuitingen*): bovenaan per insect een regel met het
  aantal nieuw gevangen insecten van de hele tuin per dag, naast de bespuitingen. Trips, witte vlieg en
  mineervlieg van de Trap-Eyes (camera boven de vangplaat, ± 3 foto's per week, alleen tuin 3); Duponchelia en
  turkse mot van de PATS-C (insectensensor, per dag van 12 tot 12 uur, beide tuinen). Een 0 staat in grijs. Klik
  op een getal voor de telling per vangplaat of sensor (rij en paal zoals bij PATS) en de stand op de plaat.
- `pats_import.py`: haalt elk uur (via `priva_bestanden.py`) de tellingen van de laatste 14 dagen op bij de
  PATS-API (v2, nu nog op de testserver beta.pats-c.com; `config.PATS_SERVER`) en zet ze in de nieuwe tabel
  `pats_telling`. Section "20" = tuin 3, "29" = tuin 1 (`config.PATS_SECTIONS`). Inloggen met PATS_USER en
  PATS_PASSW (in .env.taak); zonder die gegevens doet het script niets. Alleen lezen bij PATS.
- `integrations/pats.py` (de koppeling), `logic/pats.py` (rekenwerk, tests in `tests/test_pats.py`) en
  `pats_proef.py` (alles van PATS tonen, zonder op te slaan).

## [2.21.1] - 2026-10-24

### Opgelost
- Overzicht: op de tijdlijn verscheen toch nog een kader (x, y, lbl) bij aanraken: Streamlit zet zelf een tooltip
  op elk merkteken zonder eigen tooltip. Nu op elk merkteken en in de grafiek uitgezet.

## [2.21.0] - 2026-10-24

### Gewijzigd
- **Stek is verhuisd naar Registreren** (keuze *Stek* bij "Wat registreer je?", vooraan, in de volgorde van de
  teelt). Hele week invullen, stek per vak en het weekrapport voor de stekleverancier werken zoals voorheen; de
  pootweek kies je in dezelfde balk. Het tabblad Stek is weg: nu 6 tabbladen (1. Registreren … 6. Meer).

## [2.20.4] - 2026-10-24

### Gewijzigd
- **Overzicht sneller**: de vakstatus (lengte t.o.v. de referenties) werd bij elke klik opnieuw berekend, met
  ± 49.000 datumomzettingen per keer. Nu:
  - gecachet per tuin op dezelfde sleutels als de vakdata (`_nu_statussen`: wijzigingenlog + dag, 10 minuten);
  - de referenties met hun plantweek één keer per lijst bepaald (`vakstatus.referentiebasis`) in plaats van
    per vak, en de referentiepunten één keer per referentie in plaats van per dag van de groeicurve;
  - `als_datum` met `date.fromisoformat` (strptime alleen nog als terugval).
  - Gemeten (lokaal, NAS-database): Overzicht bij een klik 1,03 → 0,76 s; de inhoud van alle pagina's is gelijk
    gebleven. Tests in `tests/test_vakstatus.py`.

## [2.20.3] - 2026-10-24

### Gewijzigd
- Overzicht: de tijdlijn heeft geen tooltips meer. Het kader viel op een telefoon vaak half buiten beeld en ging
  niet meer weg; meer weten = klikken (balk → het vak, driehoekje → de middelen, watergift → de gietbeurten).

## [2.20.1] - 2026-10-23

### Opgelost
- Registreren, Lengte en gewicht gaf een fout ("cannot use 'list' as a dict key"): de breedte van de kolom
  Rijpheid (een keuzelijst) werd verkeerd berekend. Fout sinds 2.18.1.

## [2.20.0] - 2026-10-23

### Toegevoegd
- **Warmte van tuin 1 uit de Priva-bestanden**: het gerealiseerde vermogen van de warmtewisselaar (scherm
  M340.0, "W.WISSELAAR - ger vermogen", kW) maal de tijd, per volledige dag uit `overig-<datum>.jsonl`
  (`logic/warmtewisselaar.py`, tests in `tests/test_warmtewisselaar.py`). Een energieteller van de
  warmtewisselaar staat niet in de bestanden. 22-10-2026: 22,4 GJ.
  - Alleen dagen waar nog geen warmte staat; de Energie-export (CSV) overschrijft het gewoon.
  - Het scherm M340.0 werd elke 15 minuten gelezen; op 1 minuut (in `scripts\schermen-termijnen.csv` van de
    poller op de Priva-pc van tuin 1) wordt het nauwkeuriger. Eerst naast de Energie-export vergelijken.

## [2.19.1] - 2026-10-22

### Gewijzigd
- Overzicht, weergaven Standaard en Watergift: achter het vaknummer het totaal gegoten van de lopende teelt
  sinds het planten (l/m², bijv. "Vak 2 · 107"), zoals de kolom Tot in de oude watergiftmatrix.
- Registreren: de tabellen met vakken zijn een derde zo hoog (± 6 regels zichtbaar) en scrollen.

## [2.19.0] - 2026-10-22

### Toegevoegd
- **Tuin 1 uit de Priva-bestanden op de NAS** (naast de API): klimaat per uur per afdeling met meteo (ook de
  uurgrafieken op Tuin), watergift per vak per dag en de stand van vandaag, en gas uit pulsmeter 1. De
  bestanden van tuin 1 staan in `bron historie/Tuin 1/live` en `.../historie` (sinds 20/21-10-2026).
  - `config.PRIVA_BESTANDEN`: per tuin de regelaar, de mappen en welke pulsmeter wat meet. Tuin 1 alleen
    gas: de warmte komt daar van de warmtewisselaar (energie-export), pulsmeter 2 staat op 0.
  - `priva_klimaat.py`, `priva_watergift.py` en `priva_pulsmeters.py`: `--tuin` (standaard 3) in plaats van
    `--pcu`; de regelaar in de bestanden wordt gecontroleerd, zodat gegevens nooit bij de verkeerde tuin komen
    (`logic/priva_bron.py`, tests in `tests/test_priva_bron.py`).
  - Watergift van vandaag: een kraan wordt op pagina 1 gezocht en anders op pagina 2 (bij tuin 1 staan alle
    kranen op pagina 1); alleen kranen die een vak van de tuin zijn.
  - `priva_bestanden.py` (de uurtaak) draait de drie Priva-scripts voor elke tuin; de taak zelf blijft gelijk.

### Nog uit de Priva-API (voor beide tuinen)
- Klimaat per dag (etmaal/dag/nacht, lichtsom) waar het teeltmodel mee rekent, EC/pH per gift, de losse
  gietbeurten en de watergift met bron `priva` (gaat voor de bestanden).

## [2.18.3] - 2026-10-22

### Gewijzigd
- Overzicht, weergave Bespuitingen: de middelen staan er als de afkortingen uit de klimaatregistratie (Ri, Se,
  B5, Co, IM …), met een spatie ertussen; ook de langere namen uit Agro4all ("ASPERELLO T34 Biocontrol" → As,
  "Soiltech Root & Shoot" → Rs, "Innofer Fe++" → Fe). Natrubac = Na. Zonder bekende afkorting: het eerste
  woord of de code (H, Oc). De volledige namen staan in de tooltip (`logic/klimaatregistratie.afkorting`).

## [2.18.2] - 2026-10-21

### Gewijzigd
- Overzicht: de oogstprognose staat weer op de tijdlijn (een lopende teelt loopt doorzichtig door tot de
  prognose-oogst), en de regel **Oogst** bovenaan (aantal vakken per week) is weg.
- Overzicht: onder de weeknummers twee regels, de weekdag (zo, ma, di …) en het dagnummer, ook bij 3 mnd
  (vanaf 10 px per dag; vandaag in rood).

## [2.18.1] - 2026-10-21

### Gewijzigd
- Registreren: de tabel met vakken is compact (smalle kolommen met een vaste breedte, ± een derde van de
  breedte), met kortere koppen.
- Overzicht: de standaardperiode kijkt verder terug dan vooruit (± 60 % terug, bijv. bij 3 mnd 8 weken terug
  en 4 vooruit); op een telefoon staat de periode standaard op 4 wk.
- Overzicht: dunne lichte lijnen per dag over de tijdlijn (weg als een dag smaller is dan 6 px, bij 6 mnd en
  1 jaar), en onder de weeknummers een regel met de dagen ("21", of "wo 21" als er ruimte is; vandaag rood).
- Overzicht: de watergift heeft één kleur (geen schaal meer naar het aantal liters), en de oogstprognose
  staat niet meer op de tijdlijn: een lopende teelt loopt tot vandaag (de prognose staat in de tooltip).

## [2.18.0] - 2026-10-21

### Toegevoegd
- **Tabblad 1. Registreren** in plaats van de zijbalk: Florgib, Emmers, Lengte en gewicht, Opmerking en
  Wijzigen op de volle breedte, in de tuin die bovenaan gekozen is (Beide kan hier niet).
  - Bij Florgib, Emmers en Lengte en gewicht een tabel met één regel per lopend vak: een **eigen waarde per
    vak**, of **één waarde voor alle aangevinkte vakken** (boven de tabel). De invulkolommen staan direct
    naast het vaknummer, ook handig op een telefoon.
  - Emmers voor meerdere vakken tegelijk, met per vak *Afronden*; daaronder de oogstmomenten per vak
    aanpassen of verwijderen.
  - Rechts **Nog te doen** (Florgib verwacht of over tijd, vakken in de oogst of bijna oogstrijp, vakken in
    de oogst zonder lengte) en **Laatst geregistreerd** (uit het logboek).
  - Wijzigen: de onderdelen als tabbladen naast elkaar.
  - Rekenwerk in `logic/registreren.py` (tests in `tests/test_registreren.py`).
- De app opent op Overzicht; op een telefoon op Registreren.

### Gewijzigd
- De zijbalk is weg; *Ingelogd als* en *Uitloggen* staan op Meer.
- Overzicht: de achtergrondkleuren van de prognose zijn eruit; een lopende teelt is groen tot vandaag en
  doorzichtig groen tot de prognose-oogst, een afgeronde grijs. Per teelt (plantweek) wisselen een donkere
  en een lichte tint, zodat je de teelten uit elkaar houdt. Hoeveel de prognose voor of achter loopt staat
  in de tooltip.
- Het actieve tabblad blijft groen als je er met de muis over gaat.

## [2.17.2] - 2026-10-21

### Gewijzigd
- Overzicht, weergave Bespuitingen: het watergiftstreepje is licht blauw, zodat de middelen beter opvallen.
- Overzicht, weergave Watergift leek leeg bij 3 mnd: de getallen pasten niet in een dag en bleven weg. Nu
  staan de liters er ook bij smalle dagen in (hele liters, kleiner), en EC/pH als grijs blokje met de waarde
  in de tooltip; bij 4 wk alle getallen.

## [2.17.1] - 2026-10-21

### Gewijzigd
- Overzicht: de schakelaar Detail is vervangen door **Weergave: Standaard | Bespuitingen | Watergift**.
  - *Standaard*: driehoekjes voor de bespuitingen en blauwe vakjes voor de watergift met **standaard het
    aantal l/m² erin** (groter lettertype).
  - *Bespuitingen*: grotere driehoekjes met de **middelen erachter**, ingekort tot de volgende behandeling.
  - *Watergift*: per vak drie regels, **liters, EC en pH** van de gift, en bovenaan de **EC van de
    voorregeling**.
- Wat er in een dag past (getal met of zonder decimaal, middelnamen) bepaalt de grafiek zelf uit de breedte
  van het scherm; past er niets, dan staat het in de tooltip.

## [2.17.0] - 2026-10-21

### Gewijzigd
- **Teeltoverzicht en Watergift zijn samengevoegd tot het tabblad Overzicht** (nu 6 tabbladen). Basis is de
  tijdlijn van Teeltoverzicht. Per dag staan er altijd de **bespuitingen** (driehoekje bovenin de balk, klik =
  de middelen) en de **watergift** (blauw streepje onderin, donkerder bij meer l/m²; klik = alle gietbeurten
  met EC/pH van die dag). Met de keuze **Detail** zie je één van de twee uitgebreider: *Bespuitingen* =
  grotere driehoekjes, bij de nieuwe periode **4 wk** met de middelen erbij; *Watergift* = de hele balkhoogte
  blauw met het aantal l/m² erin (4 wk met een decimaal, 3 mnd in hele liters). Onderaan een Excel-download
  van de watergift per tuin (vak × dag).
- De tijdlijn heeft geen kopregels per afdeling meer; de vakken staan in teeltvolgorde.
- Doorklikken vanaf Tuin ("Watergift in deze periode") gaat naar Overzicht met detail Watergift.

### Verwijderd
- Het **stookadvies per afdeling** (kopregel en venster) en de pagina **Watergift** met de matrix vak × dag
  en de EC/pH-regels (`ui/watergift_matrix.py`, `EC_BAND`, `PH_BAND`, `RONDE_STARTVAK`). De EC/pH per dag
  staat nog in het venster van een gietdag.

## [2.16.2] - 2026-10-20

### Gewijzigd
- `teelt_rapport.py`: Microsoft 365 staat SMTP met wachtwoord niet toe ("SmtpClientAuthentication is disabled
  for the Tenant"). Nu ook **Direct Send**: op poort 25 zonder inloggen afleveren bij
  `tanacetum-nl.mail.protection.outlook.com` (alleen ontvangers binnen tanacetum.nl; het openbare IP van de
  NAS hoort in het SPF-record). Als reserve ook versturen via Microsoft Graph (app-registratie met Mail.Send).

## [2.16.1] - 2026-10-20

### Gewijzigd
- `teelt_rapport.py`: mailen via dezelfde SMTP-server als de e-mailmeldingen van DSM, ook met SSL op poort
  465 (naast STARTTLS op 587); `--test ADRES` stuurt een proefmail zonder hem als verstuurd te onthouden.

## [2.16.0] - 2026-10-20

### Toegevoegd
- **Rapport "Teelt afgerond"** (`teelt_rapport.py`, opmaak in `logic/teelt_rapport.py`): zodra van een teelt
  (alle vakken uit één plantweek, beide tuinen) het laatste vak geoogst is, gaat er een mail naar
  info@tanacetum.nl met als onderwerp "Teelt afgerond; plantweek N (jaar)". Daarin per tuin, in totaal en
  voor dezelfde plantweek vorig jaar: planten, stelen, uitval, teeltduur en fasen, lengtes, oogstgewicht,
  lichtsom, etmaaltemperatuur, afwijking van de berekende etmaaltemperatuur, water, energie (warmte + gas)
  en stekcijfer; daaronder hetzelfde per vak. Dezelfde cijfers als de pagina Teelt.
- Draait elk uur mee in `priva_bestanden.py`; de tabel `teelt_rapport` onthoudt wat al gemaild is. Alleen
  teelten die vanaf 20-10-2026 zijn afgerond. Versturen via SMTP (`SMTP_SERVER`, `SMTP_GEBRUIKER`,
  `SMTP_WACHTWOORD` in `.env.taak`); zonder die instellingen wordt er niets verstuurd.

## [2.15.2] - 2026-10-16

### Toegevoegd
- Vakkenregister (Teeltoverzicht): de watergift per vak in liters (l/m² × de oppervlakte van het vak).
  Lopende vakken: *Water tot nu (l/m²)* en *Water tot nu (l)*, van planten t/m gisteren; afgeronde vakken:
  *Water (l)* naast *Water (l/m²)*.

## [2.15.1] - 2026-10-16

### Gewijzigd
- Behandelingen beter te vinden: het driehoekje op de tijdlijn is ruim twee keer zo groot (met een wit
  randje), het hoekje in de Watergift-matrix 11 in plaats van 8 px.

## [2.15.0] - 2026-10-15

### Toegevoegd
- **Historie van de behandelingen** uit het teeltlogboek "Klimaatregistratie tuin 3" (blad Overview,
  regels GBM en Bio): `klimaatregistratie_import.py`, rekenwerk in `logic/klimaatregistratie.py`. Codes in
  aaneengesloten dagcellen (en meer codes in één cel) zijn één behandeling op de eerste dag van de reeks.
  De codes en hun middel staan in `logic/klimaatregistratie.CODES` (Te = Teppeki, Ba = Batavia, Ru =
  Runner, No = Nocturn, Sc = SilicaPower, B5 = Biota 500, B8 = Biota 820, Hi = Hicure, Hy = Hypoaspis
  (gestrooid), M = MONcontrol, P = Power Food, IM = ijzer en mangaan, …); Fg (Florgib) en de tikfouten La en Ja tellen niet mee. Zonder hoeveelheden. Alleen dagen
  vóór de eerste Agro4all-behandeling in die tuin. Eerste inlezing: 3.609 behandelingen van 02-01-24 t/m
  17-09-26 (5.932 regels). Ze staan met dezelfde driehoekjes op de tijdlijn, in Watergift, de vakpopup en
  bij Teelt; de popup noemt de bron.
- Het Excel-bestand wordt op de pc omgezet naar `klimaatregistratie-tuin3.json` in de map agro4all op de
  NAS; de uurtaak (`priva_bestanden.py`) leest het in.

## [2.14.1] - 2026-10-15

### Gewijzigd
- Behandelingen uit Agro4all: de hoeveelheid (en de tankmix) is nu die **per vak**. Agro4all registreert
  het totaal; dat wordt naar rato van de m² over de vakken van de registratie verdeeld (vak 19 en 20 van
  tuin 3 krijgen als halve vakken de helft). Het totaal staat ernaast (`dosering_totaal`, `mix_totaal`)
  en in de popup op de tijdlijn.
- `agro4all_samenvoegen.py` voor de geplande Claude-taak "Agro4all-behandelingen naar de NAS" (werkdagen
  07, 12 en 17 uur): de registraties van de laatste 14 dagen samenvoegen met de export op de NAS.
  `agro4all_import.py` kan ook zelf ophalen zodra er een toegangstoken van Agro4all is (`AGRO4ALL_PAT`).

## [2.14.0] - 2026-10-15

### Toegevoegd
- **Behandelingen uit Agro4all** (gewasbescherming, biologie, voeding) per vak: `agro4all_import.py`
  (rekenwerk in `logic/agro4all.py`) leest een export van alle registraties met de vakken waarop ze zijn
  uitgevoerd en vervangt daarmee de behandelingen in de database. Registraties op de hele tuin (zonder
  vakken of op alle vakken) vallen weg. De hoeveelheid is die van de hele registratie (in de tankmix), met
  het aantal vakken erbij. Draait elk uur mee in `priva_bestanden.py` (map agro4all op de NAS).
  - **Tijdlijn**: per vak per dag een driehoekje (rood = gewasbescherming, groen = biologie, bruin =
    voeding); een klik toont de middelen, hoeveelheid, tankmix, waartegen en op welke vakken.
  - **Watergift**: een gekleurd hoekje linksonder in de dagcel, de middelen in de tooltip (de oude
    subregel met codes is weg).
  - **Vakpopup**: openklapmenu *Behandelingen* over de teelt; pagina Teelt (één tuin): de tabel
    *Behandelingen (Agro4all)* met tankmix, waartegen en op hoeveel vakken.
- Eerste export (15-10-26): 34 registraties van tuin 3 (21-09 t/m 14-10-26), waarvan 32 per vak.

### Verwijderd
- De lege plaatsvervanger `integrations/behandelingen/` (vervangen door de Agro4all-import).

## [2.13.1] - 2026-10-13

### Gewijzigd
- Tijdlijn (Teeltoverzicht): kortere labels links ("Oogst" in plaats van "Oogst per week") en geen
  minimale breedte meer voor de labelkolom, zodat de tijdlijn op een telefoon direct links begint. In de
  tooltip heet de regel nu "Vak" (was "y").
- Op een telefoon staat de tuinkeuze zonder scheidingsstreepje op een eigen regel.
- Watergift: de vaste kolommen links zijn smaller (samen 140 in plaats van 214 px): koppen Pw, Lft en
  Tot (volledige naam in de tooltip), plantweek "41" en leeftijd "5d", en de regels erboven heten
  EC uitgang, EC gift en pH gift. Op een telefoon blijft zo meer ruimte voor de dagen.

## [2.13.0] - 2026-10-13

### Toegevoegd
- **Schermnummers** voor feedback: de tabbladen heten 1. Teeltoverzicht … 7. Meer, en elke sectie en
  elk openklapmenu krijgt een volgnummer ("2.3", `layout.sectie`/`layout.uitklap`). Hoofdweergaven
  zonder kop kregen er een: Tijdlijn, de watergiftmatrix (tuinnaam) en "Tuin 1 naast Tuin 3" (Tuin en
  Teelt bij Beide).

### Gewijzigd
- **Kopbalk**: de tuinkeuze staat direct achter de tabbladknoppen op dezelfde regel, de knop Uitleg
  rechts. Tabbladknoppen iets compacter.
- Grafieken: "lichtlijn" heet nu **berekende etmaaltemperatuur** (vakpopup, stookadvies, klimaat).
- Teeltoverzicht: de weergave **Vakken nu** en de **afdelingsknoppen** zijn weg (de tijdlijn toont alles).
- Watergift: de **afdelingsknoppen** zijn weg; altijd alle afdelingen.
- Tuin (Tuin 1 / Tuin 3): **Opvallend** is weg.
- Teelt: keuzelijst Vak en het zoekveld smaller.
- Kengetaltegels (o.a. Teelt): elke tegel zo breed als de inhoud, nooit een waarde over twee regels;
  datumbereik binnen één jaar korter ("17-08 – 20-08-26").
- Stek, *Hele week invullen*: alle velden op één regel; "— niet wijzigen —" heet nu "zo laten".

## [2.12.0] - 2026-10-12

### Toegevoegd
- **Teeltstrategie op de pagina Tuin** (Tuin 1 / Tuin 3), met de streefwaarden uit de
  bedrijfsomschrijving in `config.py` (`DIF_MIN`, `STOOK_MAX`, `EC_BEREIK`, `PH_BEREIK`):
  - *Opvallend* noemt een DIF (dag − nacht) onder 2 °C (per dag, of op hoeveel dagen van de week),
    een stooktemperatuur boven 15,5 °C (hoogste uur en aantal uren), en vakken met een EC buiten
    1,0–2,0 of een pH buiten 5,0–5,5. Tuin 3 heeft geen pH-regeling: daar staat de pH er als
    signaal (niet vet).
  - *Per afdeling* heeft er de regels DIF, hoogste stooktemperatuur, EC gift en pH gift bij.
    "Verwarmingstemperatuur" heet nu Stooktemperatuur (het is de berekende stooklijn).
- Pagina Teelt, tabel *Vakken in deze teelt*: kolom **Lengte half cm** (de lengte bij de Florgib).

### Gewijzigd
- Pagina Teelt, *Vakken in deze teelt*: het resultaat (planten, geoogst, uitval, lengtes, gewicht) staat
  vooraan, zodat het zonder zijwaarts scrollen in beeld is. Bij één tuin vervalt de kolom Tuin. Een lege
  cel toont "–" in plaats van "None". Uitval blijft alleen voor afgeronde vakken.
- Watergift: de matrix heeft geen maximale hoogte meer, dus geen eigen scrollbalk. Alle vakken
  (tuin 3: 39) staan onder elkaar en de pagina scrolt. Zijwaarts (de weken) scrolt de tabel nog wel.

### Gecorrigeerd
- Pagina Teelt bij Tuin 1 / Tuin 3: licht, temperatuur, lichtlijn, warmte en water per vak bleven leeg in
  *Vakken in deze teelt* (de vakken kregen hun dagdata niet mee, anders dan bij Beide).

## [2.11.1] - 2026-10-12

### Gewijzigd
- `priva_klimaat.py` begint zonder `--vanaf` bij de laatste dag die al in de database staat
  (hooguit 3 dagen terug). Een lege database krijgt zo bij de eerste run alles uit de
  bestanden (het jaar terug), en een gat na een storing vult zich vanzelf. De uurtaak op de
  NAS vult daarmee ook productie, zonder losse aanvulling.

## [2.11.0] - 2026-10-11

### Toegevoegd
- **Pagina Tuin** (was Tuin vergelijking). De tuinkeuze kiest de weergave: Beide = de
  tuinvergelijking zoals hij was; **Tuin 1 / Tuin 3** = wat er op een **dag of in een week** in
  die tuin gebeurde (`logic/tuin_overzicht.py`):
  - *Opvallend*: een afdeling ≥ 1 °C van de lichtlijn of van een andere afdeling, ≥ 4 uur per
    dag RV ≥ 90 %, een uur boven 30 / onder 10 °C, en een verschil met de vorige dag/week (of
    vorig jaar) van ≥ 1,5 °C, ≥ 5 % RV of ≥ 25 % lichtsom, water of energie;
  - *Wat er gebeurde*: geplant, Florgib, oogst (emmers per vak), afgerond en opmerkingen; een
    klik opent het vak;
  - *Per afdeling*: de kengetallen van de tuinvergelijking per afdeling en voor de hele tuin,
    plus uit het klimaat per uur het laagste/hoogste uur, uren RV ≥ 90 %, vochtdeficit, CO₂ en
    de verwarmingstemperatuur; verloop over 12 dagen/weken;
  - *Temperatuur en RV per uur* per afdeling met buiten erbij (tuin 3); tuin 1 per dag tot de
    Priva-bestanden van tuin 1 er zijn.
- **Klimaat per uur** (`priva_klimaat.py`, tabellen `klimaat_uur` en `meteo_uur`, inlezen in
  `logic/klimaat_uur.py`): per afdeling temperatuur, RV, vochtdeficit, CO₂ en
  verwarmingstemperatuur, en buiten temperatuur, RV, straling en wind. Uit de minuutdata het
  gemiddelde per uur, daarvoor (tot 07-10-26) de waarde op het hele uur. Gecontroleerd: het
  daggemiddelde van de uren is gelijk aan het klimaat per dag van Priva (±0,1 °C).
- **`priva_bestanden.py`**: draait de pulsmeters, de watergift en het klimaat per uur achter
  elkaar, zodat de NAS-taak bij een nieuwe import niet meer aangepast hoeft te worden.
- Perioden kennen "Dag" (`logic/perioden.py`); vorig jaar = 52 weken terug (zelfde weekdag).

### Gewijzigd
- Log van `priva_pulsmeters.py`: het tijdstip staat er met "UTC" bij (de klok van de container).

## [2.10.0] - 2026-10-09

### Toegevoegd
- **Watergift uit de Priva-bestanden** (`priva_watergift.py`, inlezen in `logic/priva_watergift.py`):
  per vak (kraan 1–39) l/m², EC en pH. Afgeronde dagen uit `kraan-per-dag.csv` (Priva-scherm
  "KRAAN GISTEREN"), alleen waar nog niets staat: wat de Priva-API zette blijft staan (EC/pH
  daar nauwkeuriger). **Vandaag tot nu toe** uit `water-actueel.json` ("KRAAN VANDAAG"), elke
  run bijgewerkt; in de watergiftmatrix staat dan "stand tot nu toe". Gecontroleerd op
  08-10-26: gelijk aan de API (vak 11 en 12, 3 l/m², EC 1,7 / 1,6, pH 6,2 / 6,1).

### Gecorrigeerd
- `priva_pulsmeters.py` rekent tot de laatste dag met metingen in plaats van "gisteren" volgens
  de klok van de container (UTC): de run van 01:00 nam de dag ervoor niet mee.

## [2.9.0] - 2026-10-08

### Toegevoegd
- **Warmte en gas uit de pulsmeters** (`priva_pulsmeters.py`, rekenwerk in
  `logic/pulsmeters.py`): leest de Priva-bestanden op de NAS (map Priva: `bron historie`
  per uur, `bron live` per minuut) en zet per dag de warmte (pulsmeter 2, GJ) en het gas
  (pulsmeter 1, m³) van tuin 3 in de database. Verbruik = de toename van de tellerstand;
  een reset telt niet, een dag alleen als hij helemaal gedekt is. Standaard alleen dagen
  die nog ontbreken; cijfers uit de energie-export blijven staan. Gecontroleerd op
  okt 2025 – sep 2026: warmte 99,9 %, gas 100 % gelijk aan de export. Hiermee zijn
  28-09 t/m 07-10-26 aangevuld (NAS en productie).

## [2.8.0] - 2026-10-08

### Toegevoegd
- **Pagina Teelt** (Opzoeken en Teeltvergelijking samen): de tuinkeuze bovenaan kiest de
  weergave. Bij **Beide** de vergelijking van Tuin 1, Tuin 3 en het totaal (zoals
  Teeltvergelijking was); een klik op een vak opent het in zijn eigen tuin. Bij **Tuin 1** of
  **Tuin 3** een teelt (alle vakken uit één plantweek) of één vak met alle informatie die er
  is. De teelt blijft staan als je wisselt; zoeken op een teeltcode of vaknummer opent het vak
  in zijn eigen tuin. Bij een teelt een samenvatting, bij één vak
  alles uit de vakpopup; de vakken van de teelt staan er altijd bij. Daaronder elke bron in
  een openklapmenu: oogst, Florgib en lengtes, opmerkingen, stek, watergift, gietbeurten,
  EC/pH, klimaat, warmte en gas, het verloop van de prognose, behandelingen, teelthistorie
  en wijzigingen, en alles in één Excel-bestand. Watergift, klimaat en energie per vak van
  planten tot oogst. In de vakpopup gaat de knop *Alles over dit vak* naar deze pagina.
  Het adres /teeltvergelijking bestaat niet meer (nu /teelt).

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
- **Strakkere vergelijkingstabellen** (Teelt, Tuin vergelijking): elke groep (Bezetting &
  productie, Klimaat …) met een eigen balk en grotere titel; rijtitels groter, waarden kleiner;
  alleen horizontale lijnen (Streamlit zette om elke cel een rand), geen zebrastrepen, minder
  opvulling en waarden die nooit meer midden in een getal afbreken. Op een smal scherm schuift
  de tabel zijwaarts met de eerste kolom vast.
- Navigatieknoppen vielen op een smal scherm over elkaar zodra ze naar een tweede regel
  liepen (negatieve marge van Streamlit); nu staan ze netjes onder elkaar.
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
