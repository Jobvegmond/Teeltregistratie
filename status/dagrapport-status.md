# Statusbestand voor de dagrapport-mail

De dagrapport-mail draait om 7 uur op de klimaat-pc. De statusmonitor op de laptop (`statusmonitor.py`) kan die
pc niet zien. Daarom zet de taak na het versturen zelf een klein bestand op de NAS. Daaraan ziet de statusmonitor
of de mail vandaag gelukt is.

## Wat de taak moet doen

Na elke poging (gelukt **of** mislukt) dit bestand overschrijven:

`\\192.168.0.197\Priva\dagrapport-status.json`

Lukt schrijven in de hoofdmap van de share niet, dan mag het ook in de map waar die pc al naartoe kopieert:
`\\192.168.0.197\Priva\bron historie\Tuin 1\` of `\\192.168.0.197\Priva\bron live\`.

Inhoud:

```json
{"taak": "dagrapport", "pc": "KLIMAAT", "tijdstip": "2026-10-29T07:00:12+01:00", "status": "ok", "melding": "verstuurd"}
```

- `tijdstip`: wanneer de taak klaar was, met tijdzone (of Nederlandse tijd zonder zone).
- `status`: `"ok"` als de mail verstuurd is, anders `"fout"`.
- `melding`: bij een fout de foutmelding, anders kort wat er gebeurd is.

## Voorbeeld in PowerShell

Aan het eind van het script dat de mail verstuurt:

```powershell
$status = @{ taak = 'dagrapport'; pc = $env:COMPUTERNAME; status = 'ok'; melding = 'verstuurd' }
try {
    # ... hier het maken en versturen van het dagrapport ...
} catch {
    $status.status = 'fout'
    $status.melding = $_.Exception.Message
}
$status.tijdstip = (Get-Date).ToString('yyyy-MM-ddTHH:mm:sszzz')
$status | ConvertTo-Json -Compress | Set-Content -Encoding utf8 '\\192.168.0.197\Priva\dagrapport-status.json'
```

## Wat de statusmonitor ermee doet

- **Groen:** de status is `ok` en het bestand is van na 7 uur vandaag. Tot 7:30 telt ook dat van gisteren nog.
- **Oranje:** vandaag ontbreekt, gisteren was wel gelukt.
- **Rood:** de status is `fout`, of het bestand is ouder dan twee dagen.
- **Grijs:** er is nog geen bestand.
