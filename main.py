# main.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime
import yaml

# Módulos locales
from src.markets import fetch_watchlist
from src.calendar_util import get_free_blocks
from src.news import fetch_news


def load_config(path: str) -> Dict[str, Any]:
    """
    Carga config.yaml y, si existe, hace overlay con config.local.yaml (no versionado).
    """
    base = Path(path)
    if not base.exists():
        raise FileNotFoundError(f"No se encontró el archivo de configuración: {path}")
    with base.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    # Overlay local opcional (para secretos como la URL ICS)
    local = Path("config.local.yaml")
    if local.exists():
        with local.open("r", encoding="utf-8") as f:
            loc = yaml.safe_load(f) or {}
        for k, v in loc.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    return cfg


def fmt_hm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def main() -> None:
    cfg = load_config("config.yaml")

    # === 📈 Markets ===
    tickers: List[str] = list(cfg.get("watchlist", [])) if isinstance(cfg.get("watchlist", []), list) else []
    charts_dir: str = str(cfg.get("paths", {}).get("charts_dir", "outputs/charts"))

    df = fetch_watchlist(tickers, charts_dir)

    print("\n=== 📈 Markets (resumen) ===")
    if df is not None and not df.empty:
        for r in df.to_dict(orient="records"):
            print(
                f"{r.get('ticker','')}: ${r.get('price','')}  "
                f"({r.get('pct_d','')}% d/d)  – {r.get('signal','')}  | chart: {r.get('chart','')}"
            )
    else:
        print("⚠️ Sin info de mercados")

    # === 🗓️ Agenda (hoy) ===
    ics_path: str = str(cfg.get("paths", {}).get("calendar_ics", "data/calendar.ics"))
    min_block: int = int(cfg.get("study_blocks", {}).get("min_block_minutes", 60))
    deep_block: int = int(cfg.get("study_blocks", {}).get("deep_block_minutes", 90))

    blocks, suggestions = get_free_blocks(
        ics_path=ics_path,
        min_block=min_block,
        deep_block=deep_block,
        day_start_hour=8,
        day_end_hour=21,
    )

    print("\n=== 🗓️ Agenda (hoy) — Huecos detectados ===")
    if blocks:
        for b in blocks:
            print(f"{fmt_hm(b['start'])}–{fmt_hm(b['end'])} ({b['minutes']} min)")
    else:
        print(f"No hay huecos ≥ {min_block} min")

    print("\n=== 🎯 Sugerencias de estudio ===")
    if suggestions:
        for s in suggestions:
            print(f"{s['type']}: {fmt_hm(s['start'])}–{fmt_hm(s['end'])} ({s['minutes']} min)")
    else:
        print("Sin sugerencias")

    # === 📰 News ===
    news_cfg: Dict[str, Any] = cfg.get("news", {}) or {}
    kws: List[str] = list(news_cfg.get("keywords", ["AI", "Machine Learning", "Fintech SaaS"]))
    limit: int = int(news_cfg.get("limit", 6))
    max_age: int = int(news_cfg.get("max_age_hours", 48))
    lang: str = str(news_cfg.get("lang", "en-US"))
    region: str = str(news_cfg.get("region", "US"))

    articles = fetch_news(kws, limit=limit, max_age_hours=max_age, lang=lang, region=region)

    print(f"\n=== 📰 AI/ML & Fintech News (≤ {max_age}h) ===")
    if not articles:
        print("Sin noticias recientes con esos filtros.")
    else:
        for a in articles:
            when = a["published"].strftime("%Y-%m-%d %H:%M")
            print(f"• [{a['source']}] {a['title']}  ({when})")
            print(f"  {a['url']}")
            if a.get("snippet"):
                print(f"  – {a['snippet'][:180]}...\n")
            else:
                print()


if __name__ == "__main__":
    main()
