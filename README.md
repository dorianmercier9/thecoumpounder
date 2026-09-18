# The Compounder

Journal d'investissement personnel — édition quotidienne, watchlist PEA/CTO, zones de valorisation.

## Structure
- `data/watchlist.json` — les 16 valeurs suivies et leur méthode de valorisation assignée
- `data/latest_snapshot.json` — dernier relevé de cours et multiples (généré par le script)
- `scripts/fetch_data.py` — récupère les données de marché via yfinance
- `editions/` — éditions publiées (à venir)

## Démarrage
\`\`\`bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python scripts/fetch_data.py
\`\`\`
