# src/llm.py
from __future__ import annotations

from typing import Any, Dict, List
import json
import re
import requests
from requests.exceptions import RequestException, ReadTimeout

# ---------- Tunables ----------
TOP_N_ARTICLES = 6
SNIPPET_CHARS = 240
DEFAULT_MAX_TOKENS = 256
DEFAULT_TEMPERATURE = 0.3
# ------------------------------


def _first_text(raw: Any) -> str:
    """
    Extract the assistant text from Ollama's /api/chat response.
    Handles both dict and list (stream aggregated) shapes.
    """
    if not raw:
        return ""
    if isinstance(raw, dict):
        msg = raw.get("message") or {}
        content = msg.get("content")
        if content:
            return str(content).strip()
        # Some servers mimic OpenAI-like shape
        if "choices" in raw and raw["choices"]:
            ch0 = raw["choices"][0]
            return (
                ch0.get("message", {}).get("content")
                or ch0.get("text", "")
                or ""
            ).strip()
    if isinstance(raw, list):
        parts: List[str] = []
        for it in raw:
            msg = (it or {}).get("message", {})
            c = msg.get("content")
            if c:
                parts.append(str(c))
        return "".join(parts).strip()
    return ""


def _call_ollama(messages, model, max_tokens, temperature, timeout=35):
    payload = {
        "model": model,
        "messages": messages,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
            "top_p": 0.9,
            "repeat_penalty": 1.1,
        },
    }
    r = requests.post(
        "http://localhost:11434/api/chat",
        json=payload,
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()


def _fallback_summary(articles: List[Dict[str, Any]]) -> Dict[str, Any]:
    titles = [a.get("title", "") for a in articles[:3]]
    return {
        "summary": "High-level AI/fintech headlines: " + "; ".join(titles)
        if titles
        else "No recent AI/fintech headlines.",
        "macro": "Context: watch adoption pace, enterprise ROI and regulatory updates across AI infrastructure and applications.",
        "picks": [
            {"title": a.get("title", ""), "why": "Momentum/implications.", "link": a.get("url", "")}
            for a in articles[:3]
        ],
        "_note": "fallback",
    }


def summarize_news(articles: list[dict], ai_cfg: dict) -> dict:
    model = ai_cfg.get("model", "qwen2.5:3b-instruct")
    max_tokens = int(ai_cfg.get("max_tokens", 320))
    temperature = float(ai_cfg.get("temperature", 0.15))
    timeout = int(ai_cfg.get("timeout_sec", 35))

    # Build compact context (title + source + snippet)
    lines = []
    for i, a in enumerate(articles[:TOP_N_ARTICLES], start=1):
        title = (a.get("title") or "").strip()
        source = (a.get("source") or "").strip()
        snippet = (a.get("snippet") or "").strip()
        lines.append(f"{i}. {title} — {source}")
        if snippet:
            lines.append(f"   {snippet[:SNIPPET_CHARS]}")
    news_block = "\n".join(lines)

    system = (
        "You are an analyst writing a crisp internal morning brief for a B2B SaaS fintech/AI company. "
        "Be specific, avoid hype, use bullets, and keep it under 120 words per section."
    )
    user = f"""
News (titles + short snippets):
{news_block}

Write THREE sections:
1) Resumen del día — 3 bullets of concrete takeaways (what changed, who did what, numbers).
2) Macro — 1–2 sentences on why this matters for AI/fintech B2B (revenue, regulation, infra, GTM).
3) Picks — 2–3 lines: which 2–3 items to read first and why (one clause each).

Rules:
- No list of headlines. No generic advice. No emojis.
- Use Spanish. Keep it tight.
"""

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    try:
        raw = _call_ollama(messages, model, max_tokens, temperature, timeout=timeout)
        text = _first_text(raw)
    except Exception as e:
        # If Ollama times out or isn’t ready, degrade gracefully
        return _fallback_summary(articles) | {"_error": str(e)}

    out = {"summary": "", "macro": "", "picks": []}
    if not text:
        return _fallback_summary(articles) | {"_error": "empty_response"}

    t = text.strip()

    # crude section splits
    parts = re.split(r"(?i)\bmacro\b", t, maxsplit=1)
    if len(parts) == 2:
        out["summary"] = parts[0].strip()
        macro_and_rest = parts[1]
        parts2 = re.split(r"(?i)\bpicks?\b", macro_and_rest, maxsplit=1)
        out["macro"] = parts2[0].strip()
        if len(parts2) == 2:
            picks_block = parts2[1]
            picks_lines = [ln.strip(" -•\t") for ln in picks_block.splitlines() if ln.strip()]
            # return picks as simple strings; your template just prints them
            out["picks"] = picks_lines[:3]
    else:
        out["summary"] = t

    return out
