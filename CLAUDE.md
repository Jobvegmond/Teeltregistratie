# VEM Teeltregistratie

## UI-standaard (verplicht)

Nieuwe of aangepaste pagina's MOETEN de vaste paginaopbouw en de componenten uit `ui/` gebruiken.
De volledige standaard met voorbeelden staat in [docs/ui-standaard.md](docs/ui-standaard.md).

- Opbouw: `layout.pagina_kop()` (knop Uitleg in de kop; geen paginatitel) → `layout.filterbalk()` → samenvatting →
  hoofdweergave + `legend.legenda()` → `layout.uitklap()` → `layout.export()`.
- Filters alleen via `ui/filters.py` (tuin, periode, bladeraar, afdelingen, keuzes, zoekveld,
  weergave, schakelaar). Geen losse `st.slider`, `st.select_slider`, `st.radio`, `st.date_input`
  of `st.number_input` om te filteren.
- Tuin alleen in de kop; per pagina een modus in `TUIN_MODUS` (app.py).
- Uitleg alleen via de knop Uitleg (vaste kopjes); onder een tabel hooguit één regel
  (`uitleg_help.voetnoot()`).
- Details van een vak altijd via `vak_venster()`; elke soort informatie heeft één thuis.
- Weken: zondag t/m zaterdag via `logic/weken.py`; teeltcodes en plantweken blijven ISO.
