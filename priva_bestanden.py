"""
Alle imports uit de bestanden op de NAS achter elkaar: uit de Priva-bestanden de pulsmeters (warmte en gas),
de watergift en het klimaat per uur, voor elke tuin in config.PRIVA_BESTANDEN (tuin 3 en tuin 1), en de behandelingen uit de Agro4all-export en de historie uit de
klimaatregistratie (klimaatregistratie-tuin*.json in de map agro4all) en de vangplaattellingen van PATS
(pats_import.py, via internet). Eén taak in de Synology
Taakplanner hoeft zo niet bij elke nieuwe import aangepast te worden.

Elk script draait los; gaat er één mis, dan draaien de andere toch en sluit dit af met een foutcode
(voor de mail bij een fout). Extra argumenten (bijv. --droog of --doel productie) gaan naar alle scripts.

Synology Taakplanner (root), elk uur:
    LOG=/volume2/Appdata/VEMteelt/logs/priva-bestanden.log
    /usr/local/bin/docker run --rm -v /volume2/Priva:/priva:ro \\
        -v /volume2/Appdata/VEMteelt/agro4all:/agro4all:ro \\
        --env-file /volume2/Appdata/VEMteelt/.env.taak vemteelt-app:latest \\
        python priva_bestanden.py >> "$LOG" 2>&1
"""
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Eerst de Priva-scripts, per tuin. Agro4all vóór de klimaatregistratie: die laatste neemt alleen de dagen
# vóór de eerste Agro4all-behandeling. Het rapport "Teelt afgerond" als laatste, met alle data van dit uur erin.
PRIVA_SCRIPTS = ("priva_pulsmeters.py", "priva_watergift.py", "priva_klimaat.py")
SCRIPTS = ("agro4all_import.py", "klimaatregistratie_import.py", "pats_import.py", "teelt_rapport.py")


def main():
    from config import PRIVA_BESTANDEN
    map_ = Path(__file__).resolve().parent
    stappen = [(script, ["--tuin", str(tuin)]) for tuin in sorted(PRIVA_BESTANDEN, reverse=True)
               for script in PRIVA_SCRIPTS] + [(script, []) for script in SCRIPTS]
    fouten = []
    for script, extra in stappen:
        naam = f"{script} {' '.join(extra)}".strip()
        print(f"--- {datetime.now(timezone.utc):%d-%m-%y %H:%M} UTC {naam}", flush=True)
        if subprocess.run([sys.executable, str(map_ / script), *extra, *sys.argv[1:]], cwd=map_).returncode:
            fouten.append(naam)
    if fouten:
        print(f"FOUT in: {', '.join(fouten)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
