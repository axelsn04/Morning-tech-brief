# src/emailer.py
from __future__ import annotations

import os
import ssl
import certifi
import smtplib
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Any, Dict, List


def _build_message(subject: str, html_body: str, sender: str, to_list: List[str]) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(to_list)
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    return msg


def _read_file(path: str) -> str:
    p = Path(path)
    return p.read_text(encoding="utf-8")


def send_brief(cfg: Dict[str, Any], html_path: str) -> None:
    em = cfg.get("email", {}) or {}
    if not em.get("enabled", False):
        print("[email] Disabled in config.")
        return

    sender = str(em.get("from") or em.get("smtp", {}).get("user", "")).strip()
    to_list = [t.strip() for t in (em.get("to") or []) if t and t.strip()]
    if not sender or not to_list:
        print("[email] Missing 'from' or 'to' in config.")
        return

    smtp = em.get("smtp", {}) or {}
    host = str(smtp.get("host", "smtp.gmail.com"))
    user = str(smtp.get("user", "")).strip()
    password = str(smtp.get("password", "")).strip()
    port_ssl = int(smtp.get("port_ssl", 465))       # nuevo: 465 por defecto
    port_tls = int(smtp.get("port", 587))           # legacy: 587
    use_starttls = bool(smtp.get("starttls", True)) # dejamos true para fallback

    if not user or not password:
        print("[email] Missing SMTP user/password.")
        return

    html_body = _read_file(html_path)
    subject = "🌅 Morning Tech Brief"
    msg = _build_message(subject, html_body, sender, to_list)

    # Contexto TLS con certifi
    context = ssl.create_default_context(cafile=certifi.where())

    # 1) Intento con SSL directo (465)
    try:
        with smtplib.SMTP_SSL(host, port_ssl, context=context, timeout=30) as s:
            s.login(user, password)
            s.sendmail(sender, to_list, msg.as_string())
        print(f"[email] Sent brief to {', '.join(to_list)} via SSL:{port_ssl}")
        return
    except Exception as e_ssl:
        print(f"[email] SSL:{port_ssl} failed: {e_ssl}")

    # 2) Fallback a STARTTLS (587)
    if use_starttls:
        try:
            with smtplib.SMTP(host, port_tls, timeout=30) as s:
                s.ehlo()
                s.starttls(context=context)
                s.ehlo()
                s.login(user, password)
                s.sendmail(sender, to_list, msg.as_string())
            print(f"[email] Sent brief to {', '.join(to_list)} via STARTTLS:{port_tls}")
            return
        except Exception as e_tls:
            print(f"[email] STARTTLS:{port_tls} failed: {e_tls}")

    raise RuntimeError("SMTP send failed (both SSL and STARTTLS).")
