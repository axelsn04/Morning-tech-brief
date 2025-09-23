# main.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime
import yaml

# Local modules
from src.markets import fetch_watchlist
from src.calendar_util import get_free_blocks
from src.news import fetch_news
from src.render import render_brief
from src.llm import summarize_news
from src.emailer import send_brief  # envía el HTML por correo (si lo habilitas)

def load_config(path: str) -> Dict[str, Any]:
    """Load config.yaml and, if present, overlay with config.local.yaml (unversioned)."""
    base = Path(path)
    if not base.exists():
        raise FileNotFoundError(f"No se encontró el archivo de configuración: {path}")
    with base.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    # Optional local overlay (for secrets like ICS URL, API keys, etc.)
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
    charts_dir: str = str(cfg.get("paths", {}).get("charts_dir", "docs/charts"))  # <- para GitHub Pages
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

    # === 🧠 AI Editorial (Ollama/OpenAI) ===
    ai_cfg: Dict[str, Any] = cfg.get("ai", {}) or {}
    editorial: Dict[str, Any] = {"summary": "", "macro": "", "picks": []}
    if ai_cfg.get("enabled", True) and articles:
        editorial = summarize_news(articles, ai_cfg)
        print("\n=== 🧠 AI Editorial Summary ===")
        if editorial.get("summary"):
            print(editorial["summary"])
        if editorial.get("macro"):
            print("\nMacro:")
            print(editorial["macro"])
        if editorial.get("picks"):
            print("\nResearch picks:")
            for p in editorial["picks"]:
                print(f"- {p.get('title','')} — {p.get('why','')}")

    # === 🖨️ Render HTML (para GitHub Pages) ===
    out_html = Path("docs/index.html")
    out_html.parent.mkdir(parents=True, exist_ok=True)  # asegúrate que docs/ exista

    markets_list: List[Dict[str, Any]] = []
    if df is not None and not df.empty:
        for r in df.to_dict(orient="records"):
            chart_path = r.get("chart", "")  # p.ej. "docs/charts/NVDA.png"
            chart_url = ""
            if chart_path:
                p = Path(chart_path)
                # Queremos src relativo desde docs/ (ej. "charts/NVDA.png")
                try:
                    rel = p.relative_to(Path("docs"))
                    chart_url = str(rel).replace("\\", "/")
                except ValueError:
                    # Si por alguna razón no cuelga de docs/, lo dejamos tal cual (mejor que fallar)
                    chart_url = str(p).replace("\\", "/")
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
        # AI editorial
        "editorial_summary": editorial.get("summary", ""),
        "editorial_macro": editorial.get("macro", ""),
        "editorial_picks": editorial.get("picks", []),
        # extras shown in template
        "min_block": min_block,
        "max_age": max_age,
    }

    out_file = render_brief(context, template_path, str(out_html))
    print(f"\n🖨️  HTML generado: {out_file}")

    # === ✉️ Email (opcional) ===
    email_cfg: Dict[str, Any] = cfg.get("email", {}) or {}
    if email_cfg.get("enabled", False):
        try:
            send_brief(cfg, out_file)
            print("✉️  Email enviado con el brief adjunto.")
        except Exception as e:
            print(f"[WARN] No se pudo enviar el email: {e}")


    # === 🚀 Publicar en GitHub Pages + enviar link ===
    pub_cfg = cfg.get("publish", {}) or {}
    if pub_cfg.get("auto", True):
        import subprocess, shlex

        cmd = "scripts/publish.sh"
        print(f"[publish] Running: {cmd}")
        try:
            completed = subprocess.run(
                shlex.split(cmd),
                cwd=str(Path.cwd()),
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode == 0:
                print("[publish] OK")
            else:
                print("[publish] Non-zero exit:\n", completed.stdout, completed.stderr)
        except Exception as e:
            print(f"[publish] ERROR: {e}")

        # Enviar link por email
        site_url = pub_cfg.get("site_url", "").strip()
        if site_url:
            try:
                from src.emailer import send_pages_link
                send_pages_link(cfg, site_url)
            except Exception as e:
                print(f"[email] ERROR sending link: {e}")


if __name__ == "__main__":
    main()
