from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime
import yaml

from src.markets import fetch_watchlist
from src.calendar_util import get_free_blocks
from src.news import fetch_news
from src.render import render_brief
from src.llm import summarize_news
from src.emailer import send_brief

def load_config(path: str) -> Dict[str, Any]:
    base = Path(path)
    if not base.exists():
        raise FileNotFoundError(f"No se encontró el archivo de configuración: {path}")
    with base.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
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

def _rel_from_docs(p: str | Path) -> str:
    if not p: return ""
    q = Path(p)
    try:
        return str(q.relative_to(Path("docs"))).replace("\\", "/")
    except ValueError:
        return str(q).replace("\\", "/")

def main() -> None:
    cfg = load_config("config.yaml")

    # Markets
    tickers: List[str] = list(cfg.get("watchlist", [])) if isinstance(cfg.get("watchlist", []), list) else []
    charts_dir: str = str(cfg.get("paths", {}).get("charts_dir", "docs/charts"))
    df = fetch_watchlist(tickers, charts_dir)

    print("\n=== 📈 Markets (resumen) ===")
    if df is not None and not df.empty:
        for r in df.to_dict(orient="records"):
            print(f"{r.get('ticker','')}: ${r.get('price','')}  ({r.get('pct_d','')}% d/d)  – {r.get('signal','')}  | chart: {r.get('chart','')}")
    else:
        print("⚠️ Sin info de mercados")

    # Agenda
    ics_path: str = str(cfg.get("paths", {}).get("calendar_ics", "data/calendar.ics"))
    min_block: int = int(cfg.get("study_blocks", {}).get("min_block_minutes", 60))
    deep_block: int = int(cfg.get("study_blocks", {}).get("deep_block_minutes", 90))
    blocks, suggestions = get_free_blocks(
        ics_path=ics_path, min_block=min_block, deep_block=deep_block,
        day_start_hour=8, day_end_hour=21,
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

    # News
    news_cfg: Dict[str, Any] = cfg.get("news", {}) or {}
    kws: List[str] = list(news_cfg.get("keywords", ["AI", "Machine Learning", "Fintech SaaS"]))
    limit: int = int(news_cfg.get("limit", 6))
    max_age: int = int(news_cfg.get("max_age_hours", 36))
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

    # AI summary (fast, non-blocking-style)
    ai_cfg: Dict[str, Any] = cfg.get("ai", {}) or {}
    editorial: Dict[str, Any] = {"summary": "", "macro": "", "picks": []}
    if ai_cfg.get("enabled", True) and articles:
        editorial = summarize_news(articles, ai_cfg)
        print("\n=== 🧠 AI Editorial Summary ===")
        if editorial.get("summary"): print(editorial["summary"])
        if editorial.get("macro"):
            print("\nMacro:"); print(editorial["macro"])
        if editorial.get("picks"):
            print("\nResearch picks:")
            for p in editorial["picks"]:
                print(f"- {p.get('title','')} — {p.get('why','')}")

    # Render HTML (for email + Pages)
    out_html = Path("docs/index.html")
    out_html.parent.mkdir(parents=True, exist_ok=True)

    markets_list: List[Dict[str, Any]] = []
    if df is not None and not df.empty:
        for r in df.to_dict(orient="records"):
            chart_url = _rel_from_docs(r.get("chart", "")) if r.get("chart") else ""
            markets_list.append({
                "ticker": r.get("ticker", ""),
                "price": float(r.get("price", 0.0)),
                "pct_d": float(r.get("pct_d", 0.0)),
                "signal": r.get("signal", ""),
                "chart_url": chart_url,
            })

    blocks_tpl = [{"start_hm": b["start"].strftime("%H:%M"), "end_hm": b["end"].strftime("%H:%M"), "minutes": b["minutes"]} for b in blocks]
    sugg_tpl = [{"type": s["type"], "start_hm": s["start"].strftime("%H:%M"), "end_hm": s["end"].strftime("%H:%M"), "minutes": s["minutes"]} for s in suggestions]
    news_tpl = [{"title": a["title"], "url": a["url"], "source": a["source"], "published_hm": a["published"].strftime("%Y-%m-%d %H:%M"), "snippet": " ".join(a.get("snippet", "").split())[:220]} for a in (articles or [])]

    template_path = "templates/brief.html"
    context = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "markets": markets_list, "blocks": blocks_tpl, "suggestions": sugg_tpl, "news": news_tpl,
        "editorial_summary": editorial.get("summary", ""), "editorial_macro": editorial.get("macro", ""),
        "editorial_picks": editorial.get("picks", []), "min_block": min_block, "max_age": max_age,
    }
    out_file = render_brief(context, template_path, str(out_html))
    print(f"\n🖨️  HTML generado: {out_file}")

    # Email with embedded charts; include Pages link
    pages_url = (cfg.get("publish", {}) or {}).get("site_url", "").strip()
    if (cfg.get("email", {}) or {}).get("enabled", False):
        try:
            send_brief(cfg, out_file, pages_url=pages_url)
            print("✉️  Email enviado.")
        except Exception as e:
            print(f"[WARN] No se pudo enviar el email: {e}")

if __name__ == "__main__":
    main()
