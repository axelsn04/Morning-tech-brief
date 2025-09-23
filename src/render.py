# src/render.py
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from jinja2 import Environment, FileSystemLoader, select_autoescape


def render_brief(context: Dict[str, Any], template_path: str, out_path: str) -> str:
    """Rellena la plantilla Jinja2 y guarda el HTML."""
    tpl_dir = str(Path(template_path).parent)
    tpl_name = Path(template_path).name

    env = Environment(
        loader=FileSystemLoader(tpl_dir),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template(tpl_name)

    html = template.render(**context)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return str(out.resolve())
