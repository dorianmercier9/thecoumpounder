"""
The Compounder — calcul des multiples historiques (P/E, EV/EBITDA, P/B,
FCF yield, EV/ventes) à partir des données financières annuelles et des
prix historiques.

Limite connue : yfinance ne donne gratuitement que ~4-5 exercices annuels
de données financières. C'est moins que les 5-10 ans visés dans la
méthodologie, donc ces moyennes sont une première approximation,
pas la version définitive.
"""
import json
from pathlib import Path
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent

def load_watchlist():
    with open(ROOT / "data" / "watchlist.json", encoding="utf-8") as f:
        return json.load(f)

def avg_price_for_period(hist: pd.DataFrame, start, end) -> float | None:
    window = hist.loc[(hist.index >= start) & (hist.index <= end)]
    if window.empty:
        return None
    return float(window["Close"].mean())

def get_cashflow(t: yf.Ticker):
    # yfinance a renommé cette propriété au fil des versions ; on tente les deux.
    for attr in ("cashflow", "cash_flow"):
        try:
            cf = getattr(t, attr)
            if cf is not None and not cf.empty:
                return cf
        except AttributeError:
            continue
    return None

def compute_multiples(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    hist = t.history(period="10y", interval="1mo")
    if not hist.empty:
        hist.index = hist.index.tz_localize(None)
    if hist.empty:
        return {"error": "no price history"}

    income = t.income_stmt          # colonnes = dates de clôture d'exercice
    balance = t.balance_sheet
    cashflow = get_cashflow(t)
    if income is None or income.empty:
        return {"error": "no annual financials"}

    pe_series, pb_series, ev_ebitda_series = [], [], []
    fcf_yield_series, ev_sales_series = [], []
    years_used = []

    for period_end in income.columns:
        try:
            net_income = income.loc["Net Income", period_end]
            shares = None
            for key in ("Diluted Average Shares", "Basic Average Shares"):
                if key in income.index:
                    shares = income.loc[key, period_end]
                    break
            if not shares or pd.isna(shares) or pd.isna(net_income):
                continue
            eps = net_income / shares

            year_start = period_end - pd.DateOffset(months=11)
            avg_price = avg_price_for_period(hist, year_start, period_end)
            if avg_price is None:
                continue

            if eps > 0:
                pe_series.append(avg_price / eps)

            market_cap_then = avg_price * shares
            ev_then = None

            if balance is not None and period_end in balance.columns:
                equity = balance.loc["Stockholders Equity", period_end] if "Stockholders Equity" in balance.index else None
                if equity and not pd.isna(equity) and equity > 0:
                    book_value_per_share = equity / shares
                    pb_series.append(avg_price / book_value_per_share)

                total_debt = balance.loc["Total Debt", period_end] if "Total Debt" in balance.index else 0
                cash = balance.loc["Cash And Cash Equivalents", period_end] if "Cash And Cash Equivalents" in balance.index else 0
                ev_then = market_cap_then + (total_debt or 0) - (cash or 0)

                ebitda = income.loc["EBITDA", period_end] if "EBITDA" in income.index else None
                if ebitda and not pd.isna(ebitda) and ebitda > 0:
                    ev_ebitda_series.append(ev_then / ebitda)

            # EV/ventes : besoin de l'EV (calculé ci-dessus) et du chiffre d'affaires.
            revenue = income.loc["Total Revenue", period_end] if "Total Revenue" in income.index else None
            if ev_then is not None and revenue and not pd.isna(revenue) and revenue > 0:
                ev_sales_series.append(ev_then / revenue)

            # FCF yield : ligne "Free Cash Flow" directe si dispo, sinon
            # Operating Cash Flow + Capital Expenditure (déjà négatif chez yfinance).
            fcf_then = None
            if cashflow is not None and period_end in cashflow.columns:
                if "Free Cash Flow" in cashflow.index:
                    fcf_then = cashflow.loc["Free Cash Flow", period_end]
                elif "Operating Cash Flow" in cashflow.index and "Capital Expenditure" in cashflow.index:
                    ocf = cashflow.loc["Operating Cash Flow", period_end]
                    capex = cashflow.loc["Capital Expenditure", period_end]
                    if not pd.isna(ocf) and not pd.isna(capex):
                        fcf_then = ocf + capex
            if fcf_then is not None and not pd.isna(fcf_then) and fcf_then > 0 and market_cap_then:
                fcf_yield_series.append(fcf_then / market_cap_then)
            # Un FCF négatif sur un exercice n'est pas une aberration à exclure,
            # mais un rendement négatif n'a pas de sens pour une moyenne — on l'omet
            # simplement de la série plutôt que de fausser la moyenne.

            years_used.append(str(period_end.date()))
        except (KeyError, TypeError):
            continue

    def summarize(series, ndigits=2):
        if not series:
            return None
        sorted_vals = sorted(series)
        mid = len(sorted_vals) // 2
        median = (sorted_vals[mid] if len(sorted_vals) % 2 else (sorted_vals[mid - 1] + sorted_vals[mid]) / 2)
        # Exclut une valeur qui s'écarte de plus de 3x la médiane de la série —
        # signe quasi certain d'une aberration de données plutôt qu'un vrai multiple.
        kept, excluded = [], []
        for v in series:
            if median > 0 and (v > median * 3 or v < median / 3):
                excluded.append(round(v, ndigits))
            else:
                kept.append(v)
        if not kept:
            kept = series  # si tout est jugé aberrant, on garde tout plutôt que de renvoyer vide
            excluded = []
        return {
            "average": round(sum(kept) / len(kept), ndigits),
            "n_years": len(kept),
            "values": [round(v, ndigits) for v in kept],
            "excluded_as_outliers": excluded,
        }

    return {
        "years_used": years_used,
        "pe_history": summarize(pe_series),
        "pb_history": summarize(pb_series),
        "ev_ebitda_history": summarize(ev_ebitda_series),
        "ev_sales_history": summarize(ev_sales_series),
        "fcf_yield_history": summarize(fcf_yield_series, ndigits=4),
    }

def main():
    watchlist = load_watchlist()
    results = {}
    for group, companies in watchlist.items():
        for c in companies:
            print(f"Historique {c['name']} ({c['ticker']})...")
            try:
                results[c["ticker"]] = {"name": c["name"], **compute_multiples(c["ticker"])}
            except Exception as e:
                results[c["ticker"]] = {"name": c["name"], "error": str(e)}
                print(f"  Erreur : {e}")

    out_path = ROOT / "data" / "history_multiples.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nTerminé. Résultats dans {out_path}")

    print("\nRécapitulatif du nombre d'exercices exploités par valeur :")
    for ticker, r in results.items():
        n = len(r.get("years_used", []))
        flag = " (peu de recul, à interpréter avec prudence)" if n < 3 else ""
        print(f"  {ticker}: {n} exercice(s){flag}")

if __name__ == "__main__":
    main()
