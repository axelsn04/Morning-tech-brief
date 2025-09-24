from __future__ import annotations
import os, ssl, smtplib, certifi, mimetypes, re
from pathlib import Path
from typing import Any, Dict, List, Tuple
from email.utils import formatdate
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email import encoders

def _read(p: str) -> str:
    return Path(p).read_text(encoding="utf-8")

def _smtp_send(host, user, password, sender, to_list, msg, prefer_ssl=True, port_ssl=465, port_tls=587) -> str:
    ctx = ssl.create_default_context(cafile=certifi.where())
    last_err = None
    if prefer_ssl:
        try:
            with smtplib.SMTP_SSL(host, port_ssl, context=ctx, timeout=30) as s:
                s.login(user, password)
                s.sendmail(sender, to_list, msg.as_string())
            return f"SSL:{port_ssl}"
        except Exception as e:
            last_err = e
    try:
        with smtplib.SMTP(host, port_tls, timeout=30) as s:
            s.ehlo(); s.starttls(context=ctx); s.ehlo()
            s.login(user, password)
            s.sendmail(sender, to_list, msg.as_string())
        return f"STARTTLS:{port_tls}"
    except Exception as e:
        if last_err:
            raise RuntimeError(f"SSL failed: {last_err}; STARTTLS failed: {e}")
        raise

def _collect_images_from_html(html_path: str) -> List[Tuple[str, Path]]:
    html = _read(html_path)
    srcs = re.findall(r'<img\s+[^>]*src="([^"]+)"', html, flags=re.I)
    out: List[Tuple[str, Path]] = []
    for src in srcs:
        p = Path(src)
        if not p.is_absolute():
            p = Path(html_path).parent / src
        p = p.resolve()
        if p.exists() and p.is_file():
            out.append((src, p))
    return out

def _embed_cids(html: str, mapping: Dict[str, str]) -> str:
    def repl(m):
        src = m.group(1)
        cid = mapping.get(src)
        return f'src="cid:{cid}"' if cid else m.group(0)
    return re.sub(r'src="([^"]+)"', repl, html, flags=re.I)

def send_brief(cfg: Dict[str, Any], html_path: str, pages_url: str = "") -> None:
    em = cfg.get("email", {}) or {}
    if not em.get("enabled", False):
        print("[email] Disabled.")
        return
    sender = str(em.get("from") or "").strip()
    to_list = [t.strip() for t in (em.get("to") or []) if t and t.strip()]
    smtp = em.get("smtp", {}) or {}
    host = str(smtp.get("host", "smtp.gmail.com"))
    user = str(smtp.get("user") or sender).strip()
    password = str(smtp.get("password") or os.getenv("GMAIL_APP_PASSWORD", "")).strip()
    prefer_ssl = bool(smtp.get("prefer_ssl", True))
    port_ssl = int(smtp.get("port_ssl", 465))
    port_tls = int(smtp.get("port", 587))
    if not sender or not to_list or not user or not password:
        print("[email] Missing from/to/user/password.")
        return

    raw_html = _read(html_path)
    link_block = f"""
      <div style="margin:12px 0;padding:10px;border:1px solid #ddd;border-radius:8px">
        <strong>Live version:</strong>
        <a href="{pages_url}" target="_blank" rel="noopener">{pages_url}</a>
      </div>
    """ if pages_url else ""

    mixed = MIMEMultipart("mixed")
    mixed["Subject"] = "🌅 Morning Tech Brief"
    mixed["From"] = sender
    mixed["To"] = ", ".join(to_list)
    mixed["Date"] = formatdate(localtime=True)

    related = MIMEMultipart("related")
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText("Your Morning Tech Brief (inline charts).", "plain", "utf-8"))
    alt.attach(MIMEText(link_block + raw_html, "html", "utf-8"))
    related.attach(alt)
    mixed.attach(related)

    imgs = _collect_images_from_html(html_path)
    cid_map: Dict[str, str] = {}
    for idx, (src, path) in enumerate(imgs, start=1):
        cid = f"img{idx}@brief"
        cid_map[src] = cid
        ctype, _ = mimetypes.guess_type(str(path))
        maintype, subtype = (ctype.split("/", 1) if ctype else ("application", "octet-stream"))
        with path.open("rb") as f:
            part = MIMEBase(maintype, subtype)
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-ID", f"<{cid}>")
        part.add_header("Content-Disposition", "inline", filename=path.name)
        related.attach(part)

    if cid_map:
        # replace the last HTML part in alt
        for i in range(len(alt._payload) - 1, -1, -1):
            part = alt._payload[i]
            if isinstance(part, MIMEText) and part.get_content_subtype() == "html":
                html_text = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "ignore")
                html_text = _embed_cids(html_text, cid_map)
                alt._payload[i] = MIMEText(html_text, "html", "utf-8")
                break

    mode = _smtp_send(host, user, password, sender, to_list, mixed, prefer_ssl, port_ssl, port_tls)
    print(f"[email] Sent via {mode}")
