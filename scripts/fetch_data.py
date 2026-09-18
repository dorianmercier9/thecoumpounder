"""
The Compounder — récupération des données de marché et calcul des multiples.
Nécessite : pip install -r requirements.txt
"""
import json
from pathlib import Path
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent

# Bornes de plausibilité par métrique — en dehors de ces bornes, la valeur
# est signalée comme suspecte plutôt que publiée telle quelle.
PLAUSIBLE_BOUNDS = {
    "pe_trailing": (0, 80),
    "pe_forward": (0, 80),
    "pb": (0.15, 100),   # en dessous de 0.15, quasi toujours un bug d'échelle
    "ev_ebitda": (0, 50),
    "ev_revenue": (0, 35),
}

def load_watchlist():
    with open(ROOT / "data" / "watchlist.json", encoding="utf-8") as f:
        return json.load(f)

def load_overrides():
    path = ROOT / "data" / "overrides.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def fetch_current(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    info = t.info
    return {
        "price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "pe_trailing": info.get("trailingPE"),
        "pe_forward": info.get("forwardPE"),
        "pb": info.get("priceToBook"),
        "ev_ebitda": info.get("enterpriseToEbitda"),
        "ev_revenue": info.get("enterpriseToRevenue"),
        "fcf": info.get("freeCashflow"),
        "market_cap": info.get("marketCap"),
    }

def validate(ticker: str, name: str, data: dict, overrides: dict) -> list[str]:
    """Retourne une liste d'avertissements ; ajoute un champ 'quality' par métrique."""
    warnings = []
    data["quality"] = {}

    for metric, (low, high) in PLAUSIBLE_BOUNDS.items():
        val = data.get(metric)
        if val is None:
            data["quality"][metric] = "missing"
            continue
        if not (low <= val <= high):
            data["quality"][metric] = "suspect"
            warnings.append(
                f"{ticker} ({name}) : {metric} = {val:.3f} hors bornes plausibles [{low}, {high}]"
            )
            # Si une correction manuelle existe, on l'applique et on le signale.
            if ticker in overrides and metric in overrides[ticker]:
                corrected = overrides[ticker][metric]
                warnings.append(
                    f"  -> corrigé manuellement via overrides.json : {metric} = {corrected}"
                )
                data[metric] = corrected
                data["quality"][metric] = "corrected_manually"
        else:
            data["quality"][metric] = "ok"

    # FCF négatif : pas une erreur en soi, mais invalide certaines méthodes
    # (P_FCF, FCF_YIELD) — on le signale sans le corriger.
    if data.get("fcf") is not None and data["fcf"] < 0 and data.get("method") in ("P_FCF", "FCF_YIELD"):
        warnings.append(
            f"{ticker} ({name}) : FCF négatif ({data['fcf']:,}) — méthode '{data['method']}' inutilisable telle quelle ce jour"
        )

    return warnings

def main():
    watchlist = load_watchlist()
    overrides = load_overrides()
    results = {}
    all_warnings = []

    for group, companies in watchlist.items():
        for c in companies:
            print(f"Récupération {c['name']} ({c['ticker']})...")
            try:
                data = {"name": c["name"], "group": group, "method": c["method"], **fetch_current(c["ticker"])}
                warnings = validate(c["ticker"], c["name"], data, overrides)
                all_warnings.extend(warnings)
                results[c["ticker"]] = data
            except Exception as e:
                print(f"  Erreur sur {c['ticker']} : {e}")

    out_path = ROOT / "data" / "latest_snapshot.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\nTerminé. Résultats dans {out_path}")

    if all_warnings:
        print(f"\n⚠ {len(all_warnings)} avertissement(s) de plausibilité :")
        for w in all_warnings:
            print(f"  - {w}")
    else:
        print("\nAucune valeur hors bornes détectée.")

if __name__ == "__main__":
    main()
