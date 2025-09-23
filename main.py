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
from src.render import render_brief
from src.ics_sync import sync_ics  # ← NUEVO: descarga/actualiza el .ics


def load_config(path: str) -> Dict[str, Any]:
    """Carga config.yaml y, si existe, hace overlay con config.local.yaml (no versionado)."""
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
    ics_url: str = str(cfg.get("paths", {}).get("calendar_ics_url", ""))

    # Sincroniza el ICS desde Google Calendar (si hay URL)
    if ics_url:
        try:
            synced_path = sync_ics(ics_url, ics_path)
            print(f"[calendar] ICS actualizado → {synced_path}")
        except Exception as e:
            print(f"[WARN] No se pudo actualizar el ICS: {e}")

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

    # === 🖨️ Render HTML ===
    out_html = Path("outputs/brief.html")
    out_dir = out_html.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    markets_list: List[Dict[str, Any]] = []
    if df is not None and not df.empty:
        for r in df.to_dict(orient="records"):
            chart_path = r.get("chart", "")
            chart_url = ""
            if chart_path:
                p = Path(chart_path)
                if not p.is_absolute():
                    p = (Path.cwd() / p).resolve()
                chart_url = p.as_uri()  # file:///... para que el navegador abra el PNG local
            markets_list.append({
                "ticker": r.get("ticker", ""),
                "price": float(r.get("price", 0.0)),
                "pct_d": float(r.get("pct_d", 0.0)),
                "signal": r.get("signal", ""),
                "chart_url": chart_url,
            })

    blocks_tpl = [
        {"start_hm": b["start"].strftime("%H:%M"),
         "end_hm": b["end"].strftime("%H:%M"),
         "minutes": b["minutes"]}
        for b in blocks
    ]
    sugg_tpl = [
        {"type": s["type"],
         "start_hm": s["start"].strftime("%H:%M"),
         "end_hm": s["end"].strftime("%H:%M"),
         "minutes": s["minutes"]}
        for s in suggestions
    ]
    news_tpl = [
        {"title": a["title"],
         "url": a["url"],
         "source": a["source"],
         "published_hm": a["published"].strftime("%Y-%m-%d %H:%M"),
         "snippet": " ".join(a.get("snippet", "").split())[:220]}
        for a in (articles or [])
    ]

    template_path = "templates/brief.html"
    context = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "markets": markets_list,
        "blocks": blocks_tpl,
        "suggestions": sugg_tpl,
        "news": news_tpl,
        "min_block": min_block,
        "max_age": max_age,
    }
    out_file = render_brief(context, template_path, str(out_html))
    print(f"\n🖨️  HTML generado: {out_file}")


if __name__ == "__main__":
    main()
