# src/calendar_util.py
from __future__ import annotations

from datetime import datetime, time
from typing import Any, Dict, List, Tuple
from icalendar import Calendar
import requests  # ya viene como dep. indirecta; opcional añadir a requirements.txt

def _as_datetime(x: Any, default_hour: int = 9, default_minute: int = 0) -> datetime:
    if isinstance(x, datetime):
        return x.replace(tzinfo=None)
    return datetime.combine(x, time(default_hour, default_minute))

def _load_calendar_from_url(url: str) -> Any:
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return Calendar.from_ical(resp.content)  # type: ignore[arg-type]
    except Exception as e:
        print(f"[WARN] No se pudo descargar ICS desde URL: {e}")
        return None

def _load_calendar_from_file(path: str) -> Any:
    try:
        with open(path, "rb") as f:
            data = f.read()
        return Calendar.from_ical(data)  # type: ignore[arg-type]
    except FileNotFoundError:
        print(f"[WARN] No se encontró {path}.")
        return None
    except Exception as e:
        print(f"[WARN] No se pudo leer {path}: {e}")
        return None

def _load_calendar(ics_source: str) -> Any:
    if ics_source.lower().startswith(("http://", "https://")):
        return _load_calendar_from_url(ics_source)
    return _load_calendar_from_file(ics_source)

def get_free_blocks(
    ics_path: str,
    min_block: int = 60,
    deep_block: int = 90,
    day_start_hour: int = 8,
    day_end_hour: int = 21,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    cal = _load_calendar(ics_path)
    if cal is None:
        return [], []

    today = datetime.now().date()

    events: List[Tuple[datetime, datetime]] = []
    for comp in cal.walk("vevent"):
        dtstart_prop = comp.get("dtstart")
        dtend_prop = comp.get("dtend")
        if dtstart_prop is None or dtend_prop is None:
            continue
        s = _as_datetime(dtstart_prop.dt)
        e = _as_datetime(dtend_prop.dt)
        start, end = (s, e) if s <= e else (e, s)
        if start.date() == today:
            events.append((start, end))

    events.sort(key=lambda x: x[0])

    day_start = datetime.combine(today, time(day_start_hour, 0))
    day_end = datetime.combine(today, time(day_end_hour, 0))

    blocks: List[Dict[str, Any]] = []
    cursor = day_start

    for s, e in events:
        if s > cursor:
            delta_min = int((s - cursor).total_seconds() // 60)
            if delta_min >= min_block:
                blocks.append({"start": cursor, "end": s, "minutes": delta_min})
        if e > cursor:
            cursor = e

    if day_end > cursor:
        delta_min = int((day_end - cursor).total_seconds() // 60)
        if delta_min >= min_block:
            blocks.append({"start": cursor, "end": day_end, "minutes": delta_min})

    suggestions: List[Dict[str, Any]] = []
    deep_used = False
    for b in blocks:
        kind = "Deep work" if (not deep_used and b["minutes"] >= deep_block) else "Focus"
        if kind == "Deep work":
            deep_used = True
        suggestions.append(
            {"type": kind, "start": b["start"], "end": b["end"], "minutes": b["minutes"]}
        )

    return blocks, suggestions
