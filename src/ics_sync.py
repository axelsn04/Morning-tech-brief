# src/ics_sync.py
from __future__ import annotations
from pathlib import Path
from typing import List, Union
import requests

def download_ics(url: str, dest: Union[str, Path]) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    dest.write_bytes(r.content)
    return dest

def sync_ics(urls: Union[str, List[str]], dest_path: Union[str, Path]) -> Path:
    """
    Si pasas una lista de URLs, por ahora guardamos la primera.
    (Más abajo te digo cómo soportar múltiples calendarios si quieres.)
    """
    if isinstance(urls, list):
        url = urls[0]
    else:
        url = urls
    return download_ics(url, dest_path)
