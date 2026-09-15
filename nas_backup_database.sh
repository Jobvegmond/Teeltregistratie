#!/bin/bash
# Nachtelijke back-up van de PostgreSQL-database naar de HDD's (RAID 1).
#
# Reden: de database staat op de SSD, en die is een losse schijf zonder
# redundantie. Gaat hij stuk, dan is de database weg.
#
# Plaatsen in: DSM > Configuratiescherm > Taakplanner >
#              Maken > Geplande taak > Door gebruiker gedefinieerd script
# Gebruiker: root

set -euo pipefail

DB_USER="vem"
DB_NAAM="vem_teelt"
DOELMAP="/volume1/backup/postgres"
BEWAARDAGEN=30

# Zoek de draaiende postgres-container op zijn image, niet op zijn naam:
# die naam verandert zodra de container opnieuw wordt aangemaakt.
CONTAINER=$(docker ps --format '{{.Names}} {{.Image}}' \
    | awk '$2 ~ /(^|\/)postgres(:|$)/ {print $1; exit}')

if [ -z "$CONTAINER" ]; then
    echo "FOUT: geen draaiende postgres-container gevonden. Nu actief:"
    docker ps --format '  {{.Names}}  ({{.Image}})'
    exit 1
fi

if [ ! -d "$(dirname "$DOELMAP")" ]; then
    echo "FOUT: $(dirname "$DOELMAP") bestaat niet. Controleer het volumepad."
    exit 1
fi

mkdir -p "$DOELMAP"
BESTAND="$DOELMAP/${DB_NAAM}_$(date +%Y%m%d_%H%M).sql.gz"

docker exec "$CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAAM" | gzip > "$BESTAND"

# Een dump van een paar honderd bytes betekent dat er iets misging.
GROOTTE=$(stat -c%s "$BESTAND")
if [ "$GROOTTE" -lt 10000 ]; then
    echo "FOUT: back-up is maar $GROOTTE bytes, dat klopt niet."
    rm -f "$BESTAND"
    exit 1
fi

find "$DOELMAP" -name "${DB_NAAM}_*.sql.gz" -mtime "+$BEWAARDAGEN" -delete

echo "Back-up gereed: $BESTAND ($((GROOTTE / 1024)) kB)"
