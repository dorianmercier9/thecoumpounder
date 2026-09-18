"""
The Compounder — calcule les zones I / TI / E (prix) à partir du snapshot
du jour et des moyennes historiques.

Deux familles de logique :
- Indicateurs "multiple" (P/E, P/B, EV/EBITDA, EV/ventes, P/FCF) où
  "plus bas = moins cher" : zone I = multiple cible = moyenne x 0.90,
  TI = moyenne x 0.80, E = moyenne x 0.70.
- Indicateur "yield" (FCF yield) où "plus haut = moins cher" : zone I =
  rendement cible = moyenne / 0.90, TI = moyenne / 0.80, E = moyenne / 0.70.
Le prix correspondant est déduit du prix actuel au prorata du multiple ou
du rendement actuel, en supposant les fondamentaux stables à court terme.

Limite assumée : ce n'est PAS un DCF ni une projection — c'est une règle de
lecture simple, cohérente avec la méthode choisie par société. Voir le
document de méthodologie pour le raisonnement complet par société.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (champ dans latest_snapshot.json, clé dans history_multiples.json, libellé, style)
# style "multiple" : plus bas = moins cher. style "yield" : plus haut = moins cher.
METHOD_MAP = {
    "PE": ("pe_trailing", "pe_history", "P/E", "multiple"),
    "PE_PB": ("pe_trailing", "pe_history", "P/E (P/B en indicateur croisé)", "multiple"),
    "EV_EBITDA": ("ev_ebitda", "ev_ebitda_history", "EV/EBITDA", "multiple"),
    "PE_CASH_ADJ": ("pe_trailing", "pe_history", "P/E (non ajusté de la trésorerie ici)", "multiple"),
    "PE_NORMALIZED": ("pe_trailing", "pe_history", "P/E (non normalisé sur cycle ici)", "multiple"),
    "PB": ("pb", "pb_history", "P/B", "multiple"),
    "EV_SALES": ("ev_revenue", "ev_sales_history", "EV/ventes", "multiple"),
    "FCF_YIELD": (None, "fcf_yield_history", "Rendement du FCF (FCF yield)", "yield"),
    "P_FCF": (None, "fcf_yield_history", "P/FCF (dérivé du FCF yield historique)", "multiple_from_yield"),
}

ZONE_DISCOUNTS = {"interessant": 0.90, "tres_interessant": 0.80, "exceptionnel": 0.70}

def current_fcf_yield(data):
    fcf, market_cap = data.get("fcf"), data.get("market_cap")
    if not fcf or fcf <= 0 or not market_cap:
        return None
    return fcf / market_cap

def position_actuelle(price, zones):
    i_price = zones["interessant"]["prix_implique"]
    ti_price = zones["tres_interessant"]["prix_implique"]
    e_price = zones["exceptionnel"]["prix_implique"]
    if price > i_price:
        return "au-dessus de la zone I"
    if price > ti_price:
        return "dans la zone I"
    if price > e_price:
        return "dans la zone TI"
    return "dans ou sous la zone E"

def main():
    with open(ROOT / "data" / "latest_snapshot.json", encoding="utf-8") as f:
        snapshot = json.load(f)
    with open(ROOT / "data" / "history_multiples.json", encoding="utf-8") as f:
        history = json.load(f)

    results = {}
    skipped = []

    for ticker, data in snapshot.items():
        method = data["method"]
        price = data.get("price")

        if method not in METHOD_MAP:
            skipped.append((ticker, data["name"], method, "méthode non reconnue par ce script"))
            continue

        current_field, history_key, label, style = METHOD_MAP[method]
        hist = history.get(ticker, {}).get(history_key)

        if hist is None:
            skipped.append((ticker, data["name"], method, "historique indisponible (moins de 2 exercices exploitables ou données manquantes)"))
            continue

        avg = hist["average"]

        if style == "yield":
            current_mult = current_fcf_yield(data)
            if current_mult is None or price is None:
                skipped.append((ticker, data["name"], method, "FCF négatif, nul, ou données manquantes — rendement non calculable"))
                continue
            zones = {}
            for zone_name, discount in ZONE_DISCOUNTS.items():
                target_yield = round(avg / discount, 4)
                implied_price = round(price * (current_mult / target_yield), 2)
                zones[zone_name] = {"rendement_cible": target_yield, "prix_implique": implied_price}
            current_mult_display = round(current_mult, 4)

        elif style == "multiple_from_yield":
            current_yield = current_fcf_yield(data)
            if current_yield is None or price is None or avg <= 0:
                skipped.append((ticker, data["name"], method, "FCF négatif, nul, ou données manquantes — P/FCF non calculable"))
                continue
            current_mult = 1 / current_yield
            avg_p_fcf = 1 / avg
            zones = {}
            for zone_name, discount in ZONE_DISCOUNTS.items():
                target_mult = round(avg_p_fcf * discount, 2)
                implied_price = round(price * (target_mult / current_mult), 2)
                zones[zone_name] = {"multiple_cible": target_mult, "prix_implique": implied_price}
            avg = round(avg_p_fcf, 2)
            current_mult_display = round(current_mult, 2)

        else:  # "multiple"
            current_mult = data.get(current_field)
            if current_mult is None or price is None:
                skipped.append((ticker, data["name"], method, "multiple actuel ou historique manquant"))
                continue
            zones = {}
            for zone_name, discount in ZONE_DISCOUNTS.items():
                target_mult = round(avg * discount, 2)
                implied_price = round(price * (target_mult / current_mult), 2)
                zones[zone_name] = {"multiple_cible": target_mult, "prix_implique": implied_price}
            current_mult_display = current_mult

        results[ticker] = {
            "name": data["name"],
            "indicateur": label,
            "multiple_actuel": current_mult_display,
            "moyenne_historique": avg,
            "n_exercices_historique": hist["n_years"],
            "prix_actuel": price,
            "zones": zones,
            "position_actuelle": position_actuelle(price, zones),
        }

    out_path = ROOT / "data" / "zones.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"Zones calculées pour {len(results)} valeurs. Résultats dans {out_path}\n")
    for ticker, r in results.items():
        z = r["zones"]
        print(f"{r['name']} ({ticker}) — {r['indicateur']}, actuel {r['multiple_actuel']} vs moyenne {r['moyenne_historique']} ({r['n_exercices_historique']} ex.)")
        print(f"  Prix actuel : {r['prix_actuel']}  —  Position : {r['position_actuelle']}")
        print(f"  I  <= {z['interessant']['prix_implique']}")
        print(f"  TI <= {z['tres_interessant']['prix_implique']}")
        print(f"  E  <= {z['exceptionnel']['prix_implique']}")
        print()

    if skipped:
        print(f"⚠ {len(skipped)} valeur(s) non chiffrée(s) :")
        for ticker, name, method, reason in skipped:
            print(f"  - {name} ({ticker}, méthode {method}) : {reason}")

if __name__ == "__main__":
    main()