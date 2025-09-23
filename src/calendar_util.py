# src/calendar_util.py
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, cast

from icalendar import Calendar
from zoneinfo import ZoneInfo
from icalendar import Calendar

def _load_calendar(ics_path: str | Path) -> Calendar:
    """Read ICS and return an icalendar.Calendar (cast to please Pylance)."""
    p = Path(ics_path)
    if not p.exists():
        raise FileNotFoundError(f"ICS not found: {p}")
    # Leer como texto para complacer a los stubs de icalendar (evita warning bytes->str)
    text = p.read_text(encoding="utf-8", errors="ignore")
    return cast(Calendar, Calendar.from_ical(text))


def _to_local_dt(val: datetime | date, tz: ZoneInfo, is_end: bool = False) -> datetime:
    """
    Convert DTSTART/DTEND values to timezone-aware local datetimes.
    - If a pure date (all-day), start => 00:00 local, end => 00:00 next day local.
    - If datetime with tzinfo => astimezone(tz).
    - If naive datetime => assume it's already local and set tz.
    """
    if isinstance(val, datetime):
        if val.tzinfo is not None:
            return val.astimezone(tz)
        return val.replace(tzinfo=tz)

    # All-day: for end we use next day 00:00 (exclusive end)
    if is_end:
        return datetime(val.year, val.month, val.day, 0, 0, tzinfo=tz) + timedelta(days=1)
    return datetime(val.year, val.month, val.day, 0, 0, tzinfo=tz)


def _clip_interval(
    start: datetime, end: datetime, win_start: datetime, win_end: datetime
) -> Tuple[datetime, datetime] | None:
    """Intersect [start, end) with [win_start, win_end)."""
    s = max(start, win_start)
    e = min(end, win_end)
    if s < e:
        return s, e
    return None


def _merge_intervals(intervals: List[Tuple[datetime, datetime]]) -> List[Tuple[datetime, datetime]]:
    """Merge overlapping intervals; return sorted, non-overlapping list."""
    if not intervals:
        return []
    intervals.sort(key=lambda x: x[0])
    merged: List[Tuple[datetime, datetime]] = [intervals[0]]
    for s, e in intervals[1:]:
        ls, le = merged[-1]
        if s <= le:
            merged[-1] = (ls, max(le, e))
        else:
            merged.append((s, e))
    return merged


def _expand_events_for_range(cal: Calendar, rng_start: datetime, rng_end: datetime) -> List[Dict]:
    """
    Expand events (incl. recurrences) that overlap [rng_start, rng_end).
    Returns [{'start': dt, 'end': dt, 'summary': str, 'all_day': bool}, ...]
    """
    events: List[Dict] = []

    # Try recurring expansion; widen range by 1 day to catch long cross-day events
    start_wide = rng_start - timedelta(days=1)
    end_wide = rng_end + timedelta(days=1)
    try:
        import recurring_ical_events  # type: ignore
        comps = recurring_ical_events.of(cal).between(start_wide, end_wide)
    except Exception:
        # Fallback: no expansion (recurring exceptions may be missed)
        comps = [c for c in cal.walk("VEVENT")]

    for comp in comps:
        dtstart_field = comp.get("DTSTART")
        if not dtstart_field:
            continue
        dtend_field = comp.get("DTEND")

        raw_start = dtstart_field.dt
        raw_end = dtend_field.dt if dtend_field else (
            raw_start + timedelta(hours=1) if isinstance(raw_start, datetime)
            else datetime(raw_start.year, raw_start.month, raw_start.day, 1, 0)
        )

        is_all_day = isinstance(raw_start, date) and not isinstance(raw_start, datetime)

        events.append({
            "start": raw_start,
            "end": raw_end,
            "summary": str(comp.get("SUMMARY") or ""),
            "all_day": bool(is_all_day),
        })

    # Keep only those that actually overlap the requested range
    out: List[Dict] = []
    for ev in events:
        s, e = ev["start"], ev["end"]
        # Convert to datetimes for comparison; treat date as all-day block
        if isinstance(s, date) and not isinstance(s, datetime):
            s = datetime(s.year, s.month, s.day)
        if isinstance(e, date) and not isinstance(e, datetime):
            e = datetime(e.year, e.month, e.day)
        if s < rng_end and e > rng_start:
            ev["start"] = s
            ev["end"] = e
            out.append(ev)

    return out


# ---------------------------
# Public API
# ---------------------------

def get_free_blocks(
    ics_path: str,
    min_block: int = 60,
    deep_block: int = 90,
    day_start_hour: int = 8,
    day_end_hour: int = 21,
    tz_name: str = "America/Mexico_City",
) -> tuple[List[Dict], List[Dict]]:
    """
    Compute today's free blocks ≥ min_block minutes inside [day_start_hour, day_end_hour].
    Returns (blocks, suggestions); each block/suggestion is:
      {'start': naive_local_dt, 'end': naive_local_dt, 'minutes': int, 'type'?: 'Deep work'}
    """
    tz = ZoneInfo(tz_name)
    cal = _load_calendar(ics_path)

    today = datetime.now(tz).date()
    win_start = datetime(today.year, today.month, today.day, day_start_hour, 0, tzinfo=tz)
    win_end = datetime(today.year, today.month, today.day, day_end_hour, 0, tzinfo=tz)

    occurrences = _expand_events_for_range(cal, win_start, win_end)

    # Build busy intervals in local tz
    busy: List[Tuple[datetime, datetime]] = []
    for ev in occurrences:
        start_local = _to_local_dt(ev["start"], tz, is_end=False)
        end_local = _to_local_dt(ev["end"], tz, is_end=True)

        # Guard against zero/negative durations (malformed DTEND)
        if end_local <= start_local:
            end_local = start_local + timedelta(minutes=1)

        clipped = _clip_interval(start_local, end_local, win_start, win_end)
        if clipped:
            busy.append(clipped)

    busy = _merge_intervals(busy)

    # Compute free gaps between busy intervals
    free: List[Tuple[datetime, datetime]] = []
    cur = win_start
    for s, e in busy:
        if s > cur:
            free.append((cur, s))
        cur = max(cur, e)
    if cur < win_end:
        free.append((cur, win_end))

    # Keep only gaps ≥ min_block and return naive (tz removed) for display
    blocks: List[Dict] = []
    for s, e in free:
        mins = int((e - s).total_seconds() // 60)
        if mins >= min_block:
            blocks.append({
                "start": s.replace(tzinfo=None),
                "end": e.replace(tzinfo=None),
                "minutes": mins,
            })

    # First deep-work suggestion that fits
    suggestions: List[Dict] = []
    for blk in blocks:
        if blk["minutes"] >= deep_block:
            suggestions.append({
                "type": "Deep work",
                "start": blk["start"],
                "end": blk["end"],
                "minutes": blk["minutes"],
            })
            break

    return blocks, suggestions
