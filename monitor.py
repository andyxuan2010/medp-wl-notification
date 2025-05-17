import os
import fitz  # PyMuPDF
import smtplib
import requests
import logging
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import json

# Load .env file
load_dotenv()

# Email configuration from .env
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
SMTP_SERVER = os.getenv("SMTP_SERVER", "relais.videotron.ca")
SMTP_PORT = int(os.getenv("SMTP_PORT", "25"))
USE_AUTH = os.getenv("USE_AUTH", "False").lower() == "true"
DEBUG_MODE = os.getenv("DEBUG", "False").lower() == "true"

logging.basicConfig(filename="monitor.log", level=logging.DEBUG if DEBUG_MODE else logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")

# Load recipient groups from external file
RECIPIENTS_FILE = ".recipients"
if os.path.exists(RECIPIENTS_FILE):
    with open(RECIPIENTS_FILE, "r") as f:
        EMAIL_GROUPS = json.load(f)
    if DEBUG_MODE:
        logging.debug(f"Loaded recipient groups from {RECIPIENTS_FILE}: {EMAIL_GROUPS}")
else:
    EMAIL_GROUPS = {}
    logging.warning(".recipients file not found. No recipient groups loaded.")
    if DEBUG_MODE:
        logging.debug("EMAIL_GROUPS set to empty dictionary.")

# Targets to monitor
TARGETS = {
    "udem_medp_pdf": {
        "url": "https://admission.umontreal.ca/fileadmin/fichiers/documents/liste_attente/LA.pdf",
        "keyword": "1-450-4-0",
        "keyword2": "Année préparatoire au doctorat en médecine",
        "keyword3": "Collégiens",
        "description": "UdeM Med-P (PDF)",
        "format": "pdf",
        "email_group": "students"
    },
    "mcgill_waitlist_html": {
        "url": "https://www.mcgill.ca/medadmissions/after-youve-applied/waitlist-post-interview",
        "keyword": "med-p",
        "description": "McGill Med-P Waitlist Progress",
        "format": "html_table_row",
        "email_group": "students"
    },
    "usherbrooke_progress_html": {
        "url": "https://www.usherbrooke.ca/etudes-medecine/programmes-detudes/doctorat-en-medecine/admission/suivi-des-admissions",
        "keyword": "Contingent québécois, catégorie collégiale",
        "description": "Sherbrooke Med Admission Progress",
        "format": "html",
        "email_group": "students"
    }
}

# Logging setup


def search_html(url, keyword):
    if DEBUG_MODE:
        logging.debug(f"Searching HTML for keyword '{keyword}' at {url}")
    response = requests.get(url)
    return f"Keyword found in HTML: '{keyword}'" if keyword in response.text else None

def search_mcgill_waitlist_row(url, keyword):
    if DEBUG_MODE:
        logging.debug(f"Parsing McGill HTML table at {url} for keyword '{keyword}'")
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")
    tables = soup.find_all("table")
    for table in tables:
        if "waiting list" in table.get_text().lower():
            for row in table.find_all("tr"):
                if DEBUG_MODE:
                    logging.debug(f"Table row: {row.get_text(strip=True)}")
                if keyword.lower() in row.get_text().lower():
                    return row.get_text(strip=True)
    return None

def download_pdf_and_search(url, keyword, filename, keyword2=None, keyword3=None):
    if DEBUG_MODE:
        logging.debug(f"Downloading PDF from {url} to {filename}")
    response = requests.get(url)
    with open(filename, "wb") as f:
        f.write(response.content)
    doc = fitz.open(filename)
    text_lines = []
    for page in doc:
        page_lines = [line.strip() for line in page.get_text().split("\n") if line.strip()]
        text_lines.extend(page_lines)
        if DEBUG_MODE:
            logging.debug(f"Extracted {len(page_lines)} lines from page")

    # UdeM-specific smart sequential match
    step1 = [i for i, line in enumerate(text_lines) if keyword in line]
    for idx in step1:
        try:
            if keyword2 in text_lines[idx + 1] and keyword3 in text_lines[idx + 2]:
                final_value = text_lines[idx + 3].strip()
                if DEBUG_MODE:
                    logging.debug(f"Smart PDF match found: {text_lines[idx]} | {text_lines[idx+1]} | {text_lines[idx+2]} | Value: {final_value}")
                return final_value
        except IndexError:
            continue

    # fallback search
    full_text = " ".join(text_lines)
    if keyword in full_text:
        if DEBUG_MODE:
            logging.debug("Fallback keyword match succeeded in PDF")
        return keyword

    return None

def send_email_html(subject, results, recipients):
    if DEBUG_MODE:
        logging.debug(f"Sending email to: {recipients} with subject: {subject}")
    msg = MIMEMultipart("alternative")
    msg["From"] = EMAIL_SENDER
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject

    today = datetime.now().strftime("%Y-%m-%d")
    html = """
    <html><body>
    <p>Monitoring report:</p>
    <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; font-family: Arial;">
    <thead style="background-color: #f2f2f2;"><tr><th>Title</th><th>Date</th><th>Matched Content</th></tr></thead>
    <tbody>
    """
    for item in results:
        html += f"<tr><td><a href='{item['url']}'>{item['description']}</a></td><td>{today}</td><td>{item['matched']}</td></tr>"
    html += "</tbody></table></body></html>"

    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        if USE_AUTH:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, recipients, msg.as_string())

def run_monitor():
    if DEBUG_MODE:
        logging.debug("Starting monitor run...")
    grouped_results = {}

    for key, config in TARGETS.items():
        try:
            url = config["url"]
            keyword = config["keyword"]
            keyword2 = config.get("keyword2")
            keyword3 = config.get("keyword3")
            description = config["description"]
            fmt = config["format"]
            group = config.get("email_group", "admins")

            if DEBUG_MODE:
                logging.debug(f"Checking target: {description} ({fmt})")

            result = None
            if fmt == "pdf":
                result = download_pdf_and_search(url, keyword, f"{key}.pdf", keyword2, keyword3)
            elif fmt == "html":
                result = search_html(url, keyword)
            elif fmt == "html_table_row":
                result = search_mcgill_waitlist_row(url, keyword)

            if result:
                grouped_results.setdefault(group, []).append({
                    "description": description,
                    "url": url,
                    "matched": result
                })
                logging.info(f"Match found in {description}: {result}")

        except Exception as e:
            logging.error(f"Error processing {config['description']}: {e}")
            if EMAIL_GROUPS.get("admins"):
                send_email_html(
                    subject=f"Error in {description}",
                    results=[{"description": description, "url": url, "matched": f"ERROR: {e}"}],
                    recipients=EMAIL_GROUPS["admins"]
                )

    for group, results in grouped_results.items():
        if group in EMAIL_GROUPS:
            if DEBUG_MODE:
                logging.debug(f"Sending report email for group '{group}' with {len(results)} matched result(s).")
            send_email_html(
                subject=f"Monitoring Report – {group}",
                results=results,
                recipients=EMAIL_GROUPS[group]
            )
        else:
            if DEBUG_MODE:
                logging.debug(f"Group '{group}' not found in EMAIL_GROUPS, skipping email.")

if __name__ == "__main__":
    run_monitor()
