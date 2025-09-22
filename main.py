# main.py
from pathlib import Path
import yaml
from src.markets import fetch_watchlist

def load_config(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)

def main():
    cfg = load_config("config.yaml")
    tickers = cfg.get("watchlist", [])
    charts_dir = cfg.get("paths", {}).get("charts_dir", "outputs/charts")

    if not tickers:
        print("⚠️ No hay tickers en config.yaml > watchlist")
        return

    df = fetch_watchlist(tickers, charts_dir)

    if df.empty:
        print("⚠️ No se obtuvo información de mercados.")
        return

    # Resumen en consola
    print("\n=== 📈 Markets (resumen) ===")
    for r in df.to_dict(orient="records"):
        print(f"{r['ticker']}: ${r['price']}  ({r['pct_d']}% d/d)  – {r['signal']}  | chart: {r['chart']}")

if __name__ == "__main__":
    main()
