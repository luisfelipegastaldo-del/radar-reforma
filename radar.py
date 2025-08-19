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
        requests.head(url, timeout=20, headers=headers)
    except Exception:
        pass
    feed = feedparser.parse(url)
    items = []
    for e in feed.entries[:30]:
        title = e.get("title", "").strip()
        link = e.get("link", "").strip()
        if not title or not link:
            continue
        items.append({
            "fonte": fonte,
            "titulo": title,
            "url": norm_url(link),
            "ts_pub": e.get("published", e.get("updated", "")),
            "tipo": "RSS"
        })
    return items

def fetch_portal_reforma_list(url: str) -> list:
    """Raspagem leve da listagem de notícias no portal da Reforma (MF)"""
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(url, timeout=30, headers=headers)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    items = []
    # Heurística: links que contenham /reforma-tributaria/noticias/
    for a in soup.find_all("a", href=True):
        href = a["href"]
        txt = a.get_text(strip=True)
        if not txt:
            continue
        if "/reforma-tributaria/noticias/" in href:
            full = href if href.startswith("http") else "https://www.gov.br" + href
            items.append({
                "fonte": "PortalReforma_MF",
                "titulo": txt,
                "url": norm_url(full),
                "ts_pub": "",
                "tipo": "PORTAL"
            })
    # dedupe por url
    seen_urls, out = set(), []
    for it in items:
        if it["url"] in seen_urls:
            continue
        seen_urls.add(it["url"])
        out.append(it)
    return out[:40]

def score_item(it: dict, keywords: list) -> int:
    t = (it.get("titulo","") + " " + it.get("url","")).lower()
    s = 0
    for k in keywords:
        if k.lower() in t:
            s += 2
    if it["fonte"].startswith(("Agencia", "PortalReforma")):
        s += 1
    # RSS com timestamp publicado recebe +1
    if it.get("ts_pub"):
        s += 1
    return s

# ----------------- main -----------------
def main():
    # carregar fontes e palavras-chave
    with open("sources.yaml","r",encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    keywords = cfg.get("palavras_chave", [])
    seen = load_seen()

    items = []

    # 1) RSS oficiais
    for fsrc in cfg.get("rss", []):
        try:
            items += fetch_rss(fsrc["url"], fsrc["name"])
        except Exception as e:
            print("Erro RSS:", fsrc.get("name"), e)

    # 2) Portal da Reforma (raspagem leve)
    for p in cfg.get("portais", []):
        if p["name"] == "PortalReforma_MF":
            try:
                items += fetch_portal_reforma_list(p["url"])
            except Exception as e:
                print("Erro PortalReforma:", e)

    # 3) normalizar + dedupe por canon_id
    novos = []
    for it in items:
        cid = canon_id(it["titulo"], it["url"])
        it["id"] = cid
        if cid in seen:
            continue
        it["score"] = score_item(it, keywords)
        novos.append(it)

    # 4) ordenar por relevância (score) e limitar
    novos.sort(key=lambda x: x["score"], reverse=True)
    destaque = novos[:12]

    # 5) montar HTML do boletim
    if not destaque:
        html = f"""
        <div style="font-family:Arial,sans-serif">
          <h2>Radar da Reforma Tributária</h2>
          <p><i>{now_brt_str()}</i></p>
          <p>Nenhuma novidade relevante desde a última checagem.</p>
        </div>
        """
    else:
        lis = "".join([
            f'<li><b>[{it["fonte"]}]</b> {it["titulo"]} — '
            f'<a href="{it["url"]}">{it["url"]}</a></li>'
            for it in destaque
        ])
        html = f"""
        <div style="font-family:Arial,sans-serif">
          <h2>Radar da Reforma Tributária</h2>
          <p><i>Boletim automático — {now_brt_str()}</i></p>
          <ul>{lis}</ul>
          <hr>
          <small>Fontes: RSS oficiais (Câmara, Senado, Receita, EBC) e Portal da Reforma (MF).
          Palavras-chave monitoradas: {", ".join(keywords)}.</small>
        </div>
        """

    # 6) enviar email
    send_email_html(
        subject="Radar da Reforma Tributária — boletim",
        html_body=html,
        email_from=os.environ["EMAIL_FROM"],
        email_to=os.environ["EMAIL_TO"],
        host=os.environ["SMTP_HOST"],
        port=os.environ["SMTP_PORT"],
        user=os.environ["SMTP_USER"],
        pwd=os.environ["SMTP_PASS"],
    )

    # 7) marcar como vistos
    for it in destaque:
        seen[it["id"]] = {"ts": time.time(), "url": it["url"]}
    save_seen(seen)

if __name__ == "__main__":
    main()
