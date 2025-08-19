def send_email_html(subject, html_body, email_from, email_to, host, port, user, pwd):
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    import smtplib, ssl

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = email_from
    msg["To"] = email_to
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # Fallback robusto para a porta (evita ValueError quando vier vazio)
    port_str = (str(port) if port is not None else "").strip()
    try:
        port_int = int(port_str)
    except Exception:
        port_int = 587  # padrão seguro

    # Log mínimo (sem expor senha)
    print(f"[SMTP] host={host} port={port_str or '(vazio -> 587)'} user={user}")

    ctx = ssl.create_default_context()
    with smtplib.SMTP(host, port_int) as server:
        server.starttls(context=ctx)
        server.login(user, pwd)
        recipients = [e.strip() for e in email_to.split(",") if e.strip()]
        server.sendmail(email_from, recipients, msg.as_string())
