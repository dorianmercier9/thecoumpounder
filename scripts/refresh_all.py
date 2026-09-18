"""
The Compounder — enchaîne les trois étapes du pipeline quotidien :
fetch_data.py (snapshot du jour) -> compute_history.py (moyennes
historiques) -> apply_zones.py (zones I/TI/E + position actuelle).

Usage : python3 scripts/refresh_all.py
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STEPS = [
    ("Récupération des données du jour", "fetch_data.py"),
    ("Calcul des moyennes historiques", "compute_history.py"),
    ("Calcul des zones I/TI/E", "apply_zones.py"),
]

def run_step(label, script):
    print(f"\n{'='*60}\n{label} ({script})\n{'='*60}")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script)],
        cwd=ROOT,
    )
    if result.returncode != 0:
        print(f"\n⚠ Échec de l'étape « {label} » (code {result.returncode}). Arrêt du pipeline.")
        sys.exit(result.returncode)

def main():
    for label, script in STEPS:
        run_step(label, script)
    print(f"\n{'='*60}\nPipeline terminé. Fichiers à jour :\n"
          f"  - data/latest_snapshot.json\n"
          f"  - data/history_multiples.json\n"
          f"  - data/zones.json\n{'='*60}")

if __name__ == "__main__":
    main()