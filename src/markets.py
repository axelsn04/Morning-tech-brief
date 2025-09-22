# src/markets.py
from pathlib import Path
import pandas as pd
import yfinance as yf
import matplotlib
matplotlib.use("Agg")  # backend sin GUI
import matplotlib.pyplot as plt

def fetch_watchlist(tickers: list[str], charts_dir: str) -> pd.DataFrame:
    """
    Devuelve un DataFrame con columnas:
      ticker | price | pct_d | signal | chart
    y guarda un PNG por ticker en charts_dir.
    """
    charts = Path(charts_dir)
    charts.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []

    for t in tickers:
        df: pd.DataFrame | None = None
        try:
            df = yf.download(
                t, period="6mo", interval="1d",
                progress=False, auto_adjust=True
            )
        except Exception as e:
            print(f"[WARN] yfinance falló para {t}: {e}")
            continue

        # Pylance-friendly: valida que df es DataFrame y tiene columnas esperadas
        if df is None or df.empty or "Close" not in df.columns:
            print(f"[WARN] sin datos para {t}")
            continue

        # Serie de cierre limpia
        close = df["Close"].dropna()
        if len(close) < 2:
            print(f"[WARN] muy pocos datos para {t}")
            continue

        # MAs simples
        df = df.copy()
        df["MA20"] = df["Close"].rolling(20).mean()
        df["MA50"] = df["Close"].rolling(50).mean()

        # Cierres como escalares (sin FutureWarning)
        last_close = close.iloc[-1].item()   # -> float escalar
        prev_close = close.iloc[-2].item()   # -> float escalar

        pct_d = ((last_close / prev_close) - 1) * 100 if prev_close != 0 else 0.0
        price = last_close

        # Señal: cruce MA o movimiento >= 2%
        ma20_last = df["MA20"].iloc[-1]
        ma50_last = df["MA50"].iloc[-1]
        if pd.notna(ma20_last) and pd.notna(ma50_last) and float(ma20_last) > float(ma50_last):
            signal = "MA20>MA50 ✅"
        elif abs(pct_d) >= 2.0:
            signal = f"Movimiento {'↑' if pct_d > 0 else '↓'} {pct_d:.1f}%"
        else:
            signal = "Sin señal"

        # Gráfico (últimas ~120 velas)
        plot_df = df[["Close", "MA20", "MA50"]].tail(120)
        ax = plot_df.plot(figsize=(6, 3))
        ax.set_title(t)
        ax.set_xlabel("")
        ax.set_ylabel("Precio")
        out_path = charts / f"{t}.png"
        plt.tight_layout()
        plt.savefig(out_path)
        plt.close()

        rows.append({
            "ticker": t,
            "price": round(float(price), 2),
            "pct_d": round(float(pct_d), 2),
            "signal": signal,
            "chart": str(out_path)
        })

    return pd.DataFrame(rows)
