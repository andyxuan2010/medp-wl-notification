
from datetime import datetime
import requests
import fitz  # PyMuPDF
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# === Email Configuration ===
EMAIL_SENDER = "your_email@example.com"
EMAIL_PASSWORD = "your_password"
SMTP_SERVER = "smtp.example.com"
SMTP_PORT = 587

EMAIL_GROUPS = {
    "admins": ["admin1@example.com", "admin2@example.com"],
    "students": ["student1@example.com", "student2@example.com"],
}

# === Monitoring Targets ===
TARGETS = {
    "udem_medp_pdf": {
        "url": "https://admission.umontreal.ca/fileadmin/fichiers/documents/liste_attente/LA.pdf",
        "keyword": "1-450-4-0 Année préparatoire au doctorat en médecine Collégiens",
        "description": "UdeM Med-P (PDF)",
        "format": "pdf",
        "email_group": "admins"
    },
    "udem_waitlist_html": {
        "url": "https://admission.umontreal.ca/admission/apres-la-demande/recevoir-une-reponse/",
        "keyword": "Année préparatoire au doctorat en médecine",
        "description": "UdeM Med-P Waitlist Page",
        "format": "html",
        "email_group": "students"
    }
}

# === Utility Functions ===
def check_pdf(url, keyword, filename):
    r = requests.get(url)
    with open(filename, "wb") as f:
        f.write(r.content)
    doc = fitz.open(filename)
    for page in doc:
        for line in page.get_text().split("\n"):
            if keyword in line:
                return line
    return None

def check_html(url, keyword):
    r = requests.get(url)
    if keyword in r.text:
        return f"Keyword found in HTML: '{keyword}'"
    return None

def send_email_html(subject, tracking_data, sender, recipients):
    msg = MIMEMultipart("alternative")
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject

    today = datetime.today().strftime("%Y-%m-%d")
    html = f"""
    <html>
      <body>
        <p>Here are the latest results from your tracking system:</p>
        <table border="1" cellpadding="8" cellspacing="0"
               style="border-collapse: collapse; font-family: Arial;">
          <thead style="background-color: #f2f2f2;">
            <tr>
              <th>Title</th>
              <th>Date</th>
              <th>Matched Content</th>
            </tr>
          </thead>
          <tbody>
    """

    for item in tracking_data:
        link_html = f'<a href="{item["url"]}">{item["description"]}</a>'
        html += f"""
          <tr>
            <td>{link_html}</td>
            <td>{today}</td>
            <td>{item['matched']}</td>
          </tr>
        """

    html += """
          </tbody>
        </table>
      </body>
    </html>
    """

    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, recipients, msg.as_string())

# === Main Logic ===
def main():
    grouped_results = {}

    for key, config in TARGETS.items():
        desc = config["description"]
        url = config["url"]
        kw = config["keyword"]
        fmt = config["format"]
        group = config.get("email_group", "admins")
        recipients = EMAIL_GROUPS.get(group, [])
        if not recipients:
            print(f"No recipients for group {group}, skipping {desc}")
            continue

        print(f"Checking {desc}...")
        try:
            result = None
            if fmt == "pdf":
                result = check_pdf(url, kw, f"{key}.pdf")
            elif fmt == "html":
                result = check_html(url, kw)
        except Exception as e:
            print(f"Error checking {desc}: {e}")
            continue

        if result:
            grouped_results.setdefault(group, []).append({
                "description": desc,
                "url": url,
                "matched": result
            })

    # Send email by group
    for grp, items in grouped_results.items():
        send_email_html(f"Monitoring Alert – {grp}", items, EMAIL_SENDER, EMAIL_GROUPS[grp])
        print(f"Email sent to group {grp}")

if __name__ == "__main__":
    main()

