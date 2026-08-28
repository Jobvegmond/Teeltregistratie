# Changelog

Alle belangrijke wijzigingen aan de Teeltregistratie-app worden hier bijgehouden,
inclusief de reden erachter. Nieuwste wijzigingen staan bovenaan.

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
