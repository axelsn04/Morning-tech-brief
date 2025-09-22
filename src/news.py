# src/news.py
from __future__ import annotations

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag
from datetime import datetime, timedelta
from typing import Any, Dict, List


def build_google_news_url(query: str, lang: str = "en-US", region: str = "US") -> str:
    q = query.replace(" ", "+")
    return f"https://news.google.com/rss/search?q={q}&hl={lang}&gl={region}&ceid={region}:{lang}"


def _node_text(tag: Any) -> str:  # <- acepta Any para callar Pylance
    if tag is None:
        return ""
    try:
        return tag.get_text(strip=True)  # type: ignore[attr-defined]
    except Exception:
        try:
            return str(tag).strip()
        except Exception:
            return ""


def _parse_pubdate(val: str) -> datetime:
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            return datetime.strptime(val, fmt)
        except Exception:
            pass
    return datetime.utcnow()


def fetch_news(
    keywords: List[str],
    limit: int = 5,
    max_age_hours: int = 48,
    lang: str = "en-US",
    region: str = "US",
) -> List[Dict[str, Any]]:
    cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
    results: List[Dict[str, Any]] = []

    for kw in keywords:
        url = build_google_news_url(kw, lang, region)
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
        except Exception as e:
            print(f"[WARN] Error al obtener noticias para '{kw}': {e}")
            continue

        soup = BeautifulSoup(r.text, "xml")
        for node in soup.find_all("item"):
            if not isinstance(node, Tag):
                continue

            title = _node_text(node.find("title"))
            link = _node_text(node.find("link"))
            source = _node_text(node.find("source"))
            desc = _node_text(node.find("description"))
            pub_raw = _node_text(node.find("pubDate"))
            pub_date = _parse_pubdate(pub_raw) if pub_raw else datetime.utcnow()

            if pub_date < cutoff:
                continue

            results.append(
                {
                    "title": title,
                    "url": link,
                    "source": source or "Unknown",
                    "published": pub_date,
                    "snippet": desc,
                    "keyword": kw,
                }
            )

    results.sort(key=lambda x: x["published"], reverse=True)
    seen: set[str] = set()
    deduped: List[Dict[str, Any]] = []
    for r in results:
        u = r.get("url", "")
        if not u or u in seen:
            continue
        seen.add(u)
        deduped.append(r)
        if len(deduped) >= limit:
            break

    return deduped


if __name__ == "__main__":
    kws = ["AI", "Machine Learning", "Fintech SaaS"]
    news = fetch_news(kws, limit=5, max_age_hours=48)
    if not news:
        print("No hay noticias recientes.")
    for n in news:
        when = n["published"].strftime("%Y-%m-%d %H:%M")
        print(f"• [{n['source']}] {n['title']} ({when})")
        print(f"  {n['url']}")
        print(f"  – {n['snippet'][:200]}...\n")
