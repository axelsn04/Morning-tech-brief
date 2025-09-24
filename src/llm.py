from __future__ import annotations
import json, os
from typing import Any, Dict, List
import requests

def _call_ollama(model: str, prompt: str, temperature: float, timeout: int = 20) -> str:
    try:
        base = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
        r = requests.post(
            f"{base}/api/generate",
            json={"model": model, "prompt": prompt, "options": {"temperature": temperature}, "stream": False},
            timeout=timeout,
        )
        r.raise_for_status()
        return (r.json().get("response") or "").strip()
    except Exception:
        return ""

def _fallback_summary(articles: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Simple, deterministic backup using the first 2 headlines
    titles = [a.get("title", "") for a in articles if a.get("title")]
    summary = "Top AI/fintech headlines: " + "; ".join(titles[:2])
    picks = []
    for a in articles[:2]:
        picks.append({
            "title": f"[{a.get('source','')}] {a.get('title','')}",
            "why": (a.get("snippet") or "Notable development."),
            "link": a.get("url",""),
        })
    return {"summary": summary[:200], "macro": "", "picks": picks}

def summarize_news(articles: List[Dict[str, Any]], ai_cfg: Dict[str, Any]) -> Dict[str, Any]:
    if not articles:
        return {"summary": "", "macro": "", "picks": []}

    if not ai_cfg.get("enabled", False):
        return _fallback_summary(articles)

    compact = []
    for a in articles[:8]:
        compact.append({
            "title": a.get("title", "")[:200],
            "snippet": (a.get("snippet") or "")[:240],
            "link": a.get("url", ""),
            "source": a.get("source", ""),
        })
    prompt = (
        "You are a concise tech/finance editor. Given recent AI/fintech headlines (JSON below), "
        "write: 1) summary <=60 words; 2) Macro <=40 words; 3) 2–3 research picks as JSON array "
        "(title, why, link). Return ONLY JSON with keys: summary, macro, picks.\nHEADLINES_JSON:\n"
        + json.dumps(compact, ensure_ascii=False)
    )

    text = _call_ollama(
        model=str(ai_cfg.get("model", "qwen2.5:3b-instruct")),
        prompt=prompt,
        temperature=float(ai_cfg.get("temperature", 0.15)),
        timeout=20,
    )
    if not text:
        return _fallback_summary(articles)

    try:
        data = json.loads(text)
        picks = []
        for p in (data.get("picks") or [])[:3]:
            if isinstance(p, dict):
                picks.append({
                    "title": str(p.get("title", "")).strip(),
                    "why": str(p.get("why", "")).strip(),
                    "link": str(p.get("link", "")).strip(),
                })
        return {
            "summary": str(data.get("summary", "")).strip(),
            "macro": str(data.get("macro", "")).strip(),
            "picks": picks,
        }
    except Exception:
        # fallback if the model doesn't return JSON
        return _fallback_summary(articles)
