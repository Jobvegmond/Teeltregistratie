# Changelog

Alle belangrijke wijzigingen aan de Teeltregistratie-app worden hier bijgehouden,
inclusief de reden erachter. Nieuwste wijzigingen staan bovenaan.

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
