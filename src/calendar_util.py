from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, cast

from icalendar import Calendar as _Calendar
from zoneinfo import ZoneInfo


def _load_calendar(ics_path: str | Path) -> _Calendar:
    p = Path(ics_path)
    text = p.read_text(encoding="utf-8", errors="ignore")
    return cast(_Calendar, _Calendar.from_ical(text))


def _to_local_dt(val: datetime | date, tz: ZoneInfo, is_end: bool = False) -> datetime:
    if isinstance(val, datetime):
        if val.tzinfo is not None:
            return val.astimezone(tz)
        return val.replace(tzinfo=tz)
    if is_end:
        return datetime(val.year, val.month, val.day, 0, 0, tzinfo=tz) + timedelta(days=1)
    return datetime(val.year, val.month, val.day, 0, 0, tzinfo=tz)


def _clip_interval(
    start: datetime, end: datetime, win_start: datetime, win_end: datetime
) -> Tuple[datetime, datetime] | None:
    s = max(start, win_start)
    e = min(end, win_end)
    return (s, e) if s < e else None


def _merge_intervals(intervals: List[Tuple[datetime, datetime]]) -> List[Tuple[datetime, datetime]]:
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


def _expand_events_for_range(cal: _Calendar, rng_start: datetime, rng_end: datetime) -> List[Dict]:
    events: List[Dict] = []
    start_wide = rng_start - timedelta(days=1)
    end_wide = rng_end + timedelta(days=1)
    try:
        import recurring_ical_events  # type: ignore
        comps = recurring_ical_events.of(cal).between(start_wide, end_wide)
    except Exception:
        comps = [c for c in cal.walk("VEVENT")]

    for comp in comps:
        dtstart_field = comp.get("DTSTART")
        if not dtstart_field:
            continue
        dtend_field = comp.get("DTEND")
        raw_start = dtstart_field.dt
        if not dtend_field:
            if isinstance(raw_start, datetime):
                raw_end = raw_start + timedelta(hours=1)
            else:
                raw_end = datetime(raw_start.year, raw_start.month, raw_start.day, 1, 0)
        else:
            raw_end = dtend_field.dt

        is_all_day = isinstance(raw_start, date) and not isinstance(raw_start, datetime)
        events.append({"start": raw_start, "end": raw_end, "summary": str(comp.get("SUMMARY") or ""), "all_day": bool(is_all_day)})

    out: List[Dict] = []
    for ev in events:
        s, e = ev["start"], ev["end"]
        if isinstance(s, date) and not isinstance(s, datetime):
            s = datetime(s.year, s.month, s.day)
        if isinstance(e, date) and not isinstance(e, datetime):
            e = datetime(e.year, e.month, e.day)
        if s < rng_end and e > rng_start:
            ev["start"], ev["end"] = s, e
            out.append(ev)
    return out


def get_free_blocks(
    ics_path: str,
    min_block: int = 60,
    deep_block: int = 90,
    day_start_hour: int = 8,
    day_end_hour: int = 21,
    tz_name: str = "America/Mexico_City",
) -> tuple[List[Dict], List[Dict]]:
    """
    Always returns something:
    - If ICS is present: compute real gaps.
    - If ICS missing: default free block 08:00–21:00 and one 'Deep work' suggestion.
    """
    tz = ZoneInfo(tz_name)
    today = datetime.now(tz).date()
    win_start = datetime(today.year, today.month, today.day, day_start_hour, 0, tzinfo=tz)
    win_end = datetime(today.year, today.month, today.day, day_end_hour, 0, tzinfo=tz)

    # Try to load calendar; on failure, default to a single big free block
    try:
        cal = _load_calendar(ics_path)
        occurrences = _expand_events_for_range(cal, win_start, win_end)
        busy: List[Tuple[datetime, datetime]] = []
        for ev in occurrences:
            start_local = _to_local_dt(ev["start"], tz, is_end=False)
            end_local = _to_local_dt(ev["end"], tz, is_end=True)
            if end_local <= start_local:
                end_local = start_local + timedelta(minutes=1)
            clipped = _clip_interval(start_local, end_local, win_start, win_end)
            if clipped:
                busy.append(clipped)
        busy = _merge_intervals(busy)

        free: List[Tuple[datetime, datetime]] = []
        cur = win_start
        for s, e in busy:
            if s > cur:
                free.append((cur, s))
            cur = max(cur, e)
        if cur < win_end:
            free.append((cur, win_end))

        blocks: List[Dict] = []
        for s, e in free:
            mins = int((e - s).total_seconds() // 60)
            if mins >= min_block:
                blocks.append({"start": s.replace(tzinfo=None), "end": e.replace(tzinfo=None), "minutes": mins})

    except Exception:
        # Default free block if ICS missing/unreadable
        mins = int((win_end - win_start).total_seconds() // 60)
        blocks = [{"start": win_start.replace(tzinfo=None), "end": win_end.replace(tzinfo=None), "minutes": mins}]

    suggestions: List[Dict] = []
    for blk in blocks:
        if blk["minutes"] >= deep_block:
            suggestions.append({"type": "Deep work", "start": blk["start"], "end": blk["end"], "minutes": blk["minutes"]})
            break

    return blocks, suggestions
