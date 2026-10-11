"""
Alle imports uit de Priva-bestanden op de NAS achter elkaar: pulsmeters (warmte en gas), watergift en
klimaat per uur. Eén taak in de Synology Taakplanner hoeft zo niet bij elke nieuwe import aangepast te worden.

Elk script draait los; gaat er één mis, dan draaien de andere toch en sluit dit af met een foutcode
(voor de mail bij een fout). Extra argumenten (bijv. --droog of --doel productie) gaan naar alle drie.

Synology Taakplanner (root), elk uur:
    LOG=/volume2/Appdata/VEMteelt/logs/priva-bestanden.log
    /usr/local/bin/docker run --rm -v /volume2/Priva:/priva:ro \\
        --env-file /volume2/Appdata/VEMteelt/.env.taak vemteelt-app:latest \\
        python priva_bestanden.py >> "$LOG" 2>&1
"""
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS = ("priva_pulsmeters.py", "priva_watergift.py", "priva_klimaat.py")


def main():
    map_ = Path(__file__).resolve().parent
    fouten = []
    for script in SCRIPTS:
        print(f"--- {datetime.now(timezone.utc):%d-%m-%y %H:%M} UTC {script}", flush=True)
        if subprocess.run([sys.executable, str(map_ / script), *sys.argv[1:]], cwd=map_).returncode:
            fouten.append(script)
    if fouten:
        print(f"FOUT in: {', '.join(fouten)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
