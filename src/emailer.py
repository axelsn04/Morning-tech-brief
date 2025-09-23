# src/emailer.py
from __future__ import annotations

import os
import ssl
import smtplib
import importlib as _importlib
from pathlib import Path
from typing import Any, Dict, List, Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate

import certifi  # certificados actualizados


# ----------------- helpers -----------------
def _optional_keyring_get(service: str, account: str) -> Optional[str]:
    """
    Intenta leer desde macOS Keychain *solo* si el módulo 'keyring' existe.
    Evitamos 'importlib.util' para no gatillar warnings de Pylance.
    """
    try:
        # Intento directo a importar 'keyring'; si no está instalado -> ImportError y devolvemos None
        keyring = _importlib.import_module("keyring")  # type: ignore[reportMissingImports]
    except Exception:
        return None

    try:
        return keyring.get_password(service, account)  # type: ignore[attr-defined]
    except Exception:
        return None



def _get_password_from_config_or_env(cfg: Dict[str, Any]) -> str:
    """
    Prioridades:
    1) cfg['email']['smtp']['password']
    2) env GMAIL_APP_PASSWORD
    3) Keychain (service='morning-tech-brief', account='gmail_app_password')
    """
    em = cfg.get("email", {}) or {}
    smtp = em.get("smtp", {}) or {}
    pw = str(smtp.get("password", "") or "").strip()
    if pw:
        return pw

    pw_env = os.getenv("GMAIL_APP_PASSWORD")
    if pw_env:
        return pw_env

    pw_keychain = _optional_keyring_get("morning-tech-brief", "gmail_app_password")
    if pw_keychain:
        return pw_keychain

    raise RuntimeError(
        "No SMTP password found. Set email.smtp.password in config.local.yaml, "
        "or export GMAIL_APP_PASSWORD, o guárdalo en Keychain "
        "(service='morning-tech-brief', account='gmail_app_password')."
    )


def _build_message(subject: str, html_body: str, sender: str, to_list: List[str]) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(to_list)
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    return msg


def _read_file(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _smtp_send_any(
    host: str,
    user: str,
    password: str,
    msg: MIMEMultipart,
    to_list: List[str],
    port_ssl: int = 465,
    port_tls: int = 587,
    use_starttls: bool = True,
) -> None:
    """Intenta primero SMTP SSL:465 y si falla, hace fallback a STARTTLS:587."""
    context = ssl.create_default_context(cafile=certifi.where())

    # 1) SSL directo (465)
    try:
        with smtplib.SMTP_SSL(host, port_ssl, context=context, timeout=30) as s:
            s.login(user, password)
            s.sendmail(msg["From"], to_list, msg.as_string())
        print(f"[email] Sent via SSL:{port_ssl}")
        return
    except Exception as e_ssl:
        print(f"[email] SSL:{port_ssl} failed: {e_ssl}")

    # 2) STARTTLS (587)
    if use_starttls:
        try:
            with smtplib.SMTP(host, port_tls, timeout=30) as s:
                s.ehlo()
                s.starttls(context=context)
                s.ehlo()
                s.login(user, password)
                s.sendmail(msg["From"], to_list, msg.as_string())
            print(f"[email] Sent via STARTTLS:{port_tls}")
            return
        except Exception as e_tls:
            print(f"[email] STARTTLS:{port_tls} failed: {e_tls}")

    raise RuntimeError("SMTP send failed (both SSL and STARTTLS).")


# ----------------- API pública -----------------
def send_brief(cfg: Dict[str, Any], html_path: str) -> None:
    """Envía el brief con el HTML completo en el cuerpo del email."""
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
    user = str(smtp.get("user", "") or sender).strip()
    password = _get_password_from_config_or_env(cfg)
    port_ssl = int(smtp.get("port_ssl", 465))
    port_tls = int(smtp.get("port", 587))
    use_starttls = bool(smtp.get("starttls", True))

    html_body = _read_file(html_path)
    subject = em.get("subject_brief", "🌅 Morning Tech Brief")
    msg = _build_message(subject, html_body, sender, to_list)

    _smtp_send_any(
        host, user, password, msg, to_list,
        port_ssl=port_ssl, port_tls=port_tls, use_starttls=use_starttls
    )
    print("✉️  Email enviado con el brief adjunto.")


def send_pages_link(cfg: Dict[str, Any], pages_url: str) -> None:
    """
    Envía un email corto con el link público (GitHub Pages).
    Reutiliza el MISMO password que send_brief.
    """
    em = cfg.get("email", {}) or {}
    if not (em.get("enabled") and pages_url):
        return

    sender = str(em.get("from") or em.get("smtp", {}).get("user", "")).strip()
    to_list = [t.strip() for t in (em.get("to") or []) if t and t.strip()]
    subject = em.get("subject_link", "Morning Tech Brief (link)")

    if not sender or not to_list:
        print("[email] Missing 'from' or 'to' in config; skip send.")
        return

    html_body = f"""
    <html><body>
      <p>Buenos días ☕</p>
      <p>Tu brief está publicado en: <a href="{pages_url}" target="_blank" rel="noopener">{pages_url}</a></p>
      <p>— Bot</p>
    </body></html>
    """

    msg = MIMEMultipart("alternative")
    msg["From"] = sender
    msg["To"] = ", ".join(to_list)
    msg["Date"] = formatdate(localtime=True)
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    smtp = em.get("smtp", {}) or {}
    host = str(smtp.get("host", "smtp.gmail.com"))
    user = str(smtp.get("user", "") or sender).strip()
    password = _get_password_from_config_or_env(cfg)
    port_ssl = int(smtp.get("port_ssl", 465))
    port_tls = int(smtp.get("port", 587))
    use_starttls = bool(smtp.get("starttls", True))

    _smtp_send_any(
        host, user, password, msg, to_list,
        port_ssl=port_ssl, port_tls=port_tls, use_starttls=use_starttls
    )
    print("[email] Link de Pages enviado.")
