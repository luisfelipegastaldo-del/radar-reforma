import os, smtplib, ssl, hashlib, json, time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import requests, feedparser
from bs4 import BeautifulSoup
from dateutil import tz
import yaml

USER_AGENT = "RadarReformaBot/1.0 (+https://github.com/)"

# ----------------- util -----------------
def norm_url(u: str) -> str:
    sp = urlsplit(u)
    q = [(k, v) for (k, v) in parse_qsl(sp.query) if not k.lower().startswith("utm")]
    return urlunsplit((sp.scheme, sp.netloc, sp.path, urlencode(q, doseq=True), ""))

def canon_id(title: str, url: str) -> str:
    base = (title or "").strip().lower() + "|" + norm_url(url)
    return hashlib.sha1(base.encode("utf-8")).hexdigest()

def now_brt_str() -> str:
    brt = tz.gettz("America/Sao_Paulo")
    return datetime.now(tz=brt).strftime("%d/%m/%Y %H:%M")

def load_seen() -> dict:
    if os.path.exists("seen.json"):
        with open("seen.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_seen(seen: dict) -> None:
    with open("seen.json", "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)

def send_email_html(subject, html_body, email_from, email_to, host, port, user, pwd):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = email_from
    msg["To"] = email_to
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    ctx = ssl.create_default_context()
    with smtplib.SMTP(host, int(port)) as server:
        server.starttls(context=ctx)
        server.login(user, pwd)
        recipients = [e.strip() for e in email_to.split(",") if e.strip()]
        server.sendmail(email_from, recipients, msg.as_string())

# ----------------- coleta -----------------
def fetch_rss(url: str, fonte: str) -> list:
    headers = {"User-Agent": USER_AGENT}
    # feedparser também faz o request, mas um HEAD rápido ajuda a evitar bloqueios
    try:
        requests.head(url, timeout=20, headers=he
