# src/news.py
from __future__ import annotations

import html
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag


def _clean_text(s: str) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    # remove trailing site names duplicated in titles (common in Google RSS)
    s = re.sub(
        r"\s*[-–—]\s*(Reuters|Bloomberg|Forbes|Axios|The Verge|BBC|NYT|GeekWire|TechCrunch)\s*$",
        "",
        s,
        flags=re.I,
    )
    return s


def _smart_snippet(desc: str) -> str:
    """Prefer RSS <description>; strip boilerplate and trim."""
    txt = _clean_text(desc or "")
    txt = re.sub(r"(Read more|Continue reading).*?$", "", txt, flags=re.I)
    return (txt[:240] + "…") if len(txt) > 240 else txt


def build_google_news_url(query: str, lang: str = "en-US", region: str = "US") -> str:
    q = query.replace(" ", "+")
    return f"https://news.google.com/rss/search?q={q}&hl={lang}&gl={region}&ceid={region}:{lang}"


def _node_text(tag: Any) -> str:
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


def sanitize_snippet(raw: str, max_len: int = 220) -> str:
    if not raw:
        return ""
    unescaped = html.unescape(raw)
    try:
        _soup = BeautifulSoup(unescaped, "html.parser")
        txt = _soup.get_text(" ", strip=True)
    except Exception:
        txt = unescaped
    clean = " ".join(txt.split())
    return clean[:max_len]


def fetch_news(
    keywords: List[str],
    limit: int = 5,
    max_age_hours: int = 48,
    lang: str = "en-US",
    region: str = "US",
) -> List[Dict[str, Any]]:
    """
    Downloads recent items from Google News RSS.
    Returns: [{title, url, source, published(datetime), snippet, keyword}]
    """
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

        soup = BeautifulSoup(r.text, "xml")  # needs lxml installed
        for node in soup.find_all("item"):
            if not isinstance(node, Tag):
                continue

            title = _node_text(node.find("title"))
            link = _node_text(node.find("link"))
            source = _node_text(node.find("source"))
            desc_raw = _node_text(node.find("description"))
            pub_raw = _node_text(node.find("pubDate"))
            pub_date = _parse_pubdate(pub_raw) if pub_raw else datetime.utcnow()

            if pub_date < cutoff:
                continue

            # 🔧 FIX: use desc_raw (we accidentally referenced 'summary' before)
            # Option A (strict): sanitize HTML
            # snippet = sanitize_snippet(desc_raw, 220)
            # Option B (lighter): smart trim
            snippet = sanitize_snippet(desc_raw, 220)

            results.append(
                {
                    "title": _clean_text(title),
                    "url": link,
                    "source": source or "Unknown",
                    "published": pub_date,
                    "snippet": snippet,
                    "keyword": kw,
                }
            )

    # Sort newest first and de-duplicate by URL
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
    news = fetch_news(kws, limit=6, max_age_hours=48)
    if not news:
        print("No hay noticias recientes.")
    for n in news:
        when = n["published"].strftime("%Y-%m-%d %H:%M")
        print(f"• [{n['source']}] {n['title']} ({when})")
        print(f"  {n['url']}")
        if n.get("snippet"):
            print(f"  – {n['snippet']}\n")
        else:
            print()
