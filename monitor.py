import os
import fitz  # PyMuPDF
import smtplib
import requests
import logging
import unicodedata
import re
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
FORCE_MODE = os.getenv("FORCE", "False").lower() == "true"
SMS_RECIPIENTS = os.getenv("SMS_RECIPIENTS", "").split(",") 
DEFAULT_RECIPIENTS_FILE = os.getenv("DEFAULT_RECIPIENTS_FILE")

logging.basicConfig(filename="monitor.log", level=logging.DEBUG if DEBUG_MODE else logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")

def normalize_text(text):
    # Normalize unicode (accents, etc.) and lowercase for comparison
    return unicodedata.normalize("NFKD", text).encode("ASCII", "ignore").decode().lower().strip()

def insert_line_break_after_ordinal(text):
    # Match digits followed by an 'e' (regular or superscript-like), then insert a newline
    return re.sub(r'(\d+[eᵉ])', r'\1\n', text).strip()



SNAPSHOT_DIR = "snapshots"
os.makedirs(SNAPSHOT_DIR, exist_ok=True)

def load_previous_snapshot(snapshot_key):
    path = os.path.join(SNAPSHOT_DIR, f"{snapshot_key}.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def save_current_snapshot(snapshot_key, data):
    path = os.path.join(SNAPSHOT_DIR, f"{snapshot_key}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def has_changed(snapshot_key, new_data):
    old_data = load_previous_snapshot(snapshot_key)
    if old_data != new_data:
        save_current_snapshot(snapshot_key, new_data)
        return True
    return False


# def send_sms_notification(message, sms_recipients):
#     for sms_email in sms_recipients:
#         sms_msg = MIMEText(message)
#         sms_msg["From"] = EMAIL_SENDER
#         sms_msg["To"] = sms_email
#         sms_msg["Subject"] = ""  # SMS ignores subject

#         with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
#             if USE_AUTH:
#                 server.starttls()
#                 server.login(EMAIL_SENDER, EMAIL_PASSWORD)
#             server.sendmail(EMAIL_SENDER, [sms_email], sms_msg.as_string())

# Load recipient groups from external file
RECIPIENTS_FILE = DEFAULT_RECIPIENTS_FILE

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
        "keyword2": "Médecine (Année préparatoire au doctorat) - Campus Montréal",
        "keyword3": "Collégiens",
        "description": "UdeM Med-P WL",
        "format": "pdf",
        "email_group": "students",
        "sms_group": "sms"
    },
    "mcgill_waitlist_html": {
        "url": "https://www.mcgill.ca/medadmissions/after-youve-applied/waitlist-post-interview",
        "keyword": "Med-P",
        "description": "McGill Med-P WL",
        "format": "html_table_row",
        "email_group": "students",
        "sms_group": "sms"        
    },
    "usherbrooke_progress_html": {
        "url": "https://www.usherbrooke.ca/etudes-medecine/programmes-detudes/doctorat-en-medecine/admission/suivi-des-admissions",
        "keyword": "Contingent québécois, catégorie collégiale",
        "description": "UdeS Med-P WL",
        "format": "html_table_row",
        "email_group": "students",
        "sms_group": "sms"        
    }
}

# Logging setup


def search_html(url, keyword):
    if DEBUG_MODE:
        logging.debug(f"Searching HTML for keyword '{keyword}' at {url}")
    response = requests.get(url)
    return f"Keyword found in HTML: '{keyword}'" if keyword in response.text else None

def search_waitlist_row(url, keyword):
    if DEBUG_MODE:
        logging.debug(f"Parsing HTML table at {url} for keyword '{keyword}'")
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")
    tables = soup.find_all("table")

    normalized_keyword = normalize_text(keyword)

    for table in tables:
        logging.debug(f"Table: {table.get_text(strip=True)}")    
        for row in table.find_all("tr"):
            logging.debug(f"Row: {row.get_text(strip=True)}")
            cells = row.find_all(["td", "th"])
            if not cells:
                continue

            cell_text = normalize_text(cells[0].get_text())
            logging.debug(f"Normalized Cell Text: {cell_text}")

            if normalized_keyword in cell_text:
                positions_text = cells[1].get_text()
                logging.info(f"Match found: {cell_text} | {positions_text}")
                return insert_line_break_after_ordinal(positions_text.strip())
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
            logging.debug(f"Extracted {len(page_lines)} lines from page {page}")

    # UdeM-specific smart sequential match
    step1 = [i for i, line in enumerate(text_lines) if keyword in line]
    for idx in step1:
        try:
            if keyword2 in text_lines[idx + 1] and keyword3 in text_lines[idx + 2]:
                final_value = text_lines[idx + 3].strip()
                if DEBUG_MODE:
                    logging.debug(f"Smart PDF match found: {text_lines[idx]} | {text_lines[idx+1]} | {text_lines[idx+2]} | Value: {final_value}")
                logging.info(f"Smart PDF match found: {text_lines[idx]} | {text_lines[idx+1]} | {text_lines[idx+2]} | Value: {final_value}")    
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

def send_email_html(subject, results, email_recipients, sms_recipients):
    admin = EMAIL_GROUPS["admins"]
    #sms_recipients = EMAIL_GROUPS.get("sms", [])
    if DEBUG_MODE:
        logging.debug(f"Sending email to admins: {admin} with BCC to recipients: {email_recipients}")
        logging.debug(f"Also sending SMS notification to: {sms_recipients}")

    msg = MIMEMultipart("alternative")
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_SENDER 
    msg["Subject"] = subject

    today = datetime.now().strftime("%Y-%m-%d")
    html = """
    <html><body>
    <p>Quebec Med-P Program Waiting List Tracking System</p>
    <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; font-family: Arial;">
    <thead style="background-color: #f2f2f2;"><tr><th>Title</th><th>Date</th><th>Offer Position</th></tr></thead>
    <tbody>
    """
    for item in results:
        html += f"<tr><td><a href='{item['url']}'>{item['description']}</a></td><td>{today}</td><td>{item['matched']}</td></tr>"
    html += "</tbody></table></body></html>"

    msg.attach(MIMEText(html, "html"))

    sms_lines = ["Med-P Update:"]
    for item in results:
        sms_lines.append(f"• {item['description']}: {item['matched']}")
    sms_message = "\n".join(sms_lines)


    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        if USE_AUTH:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        
        server.sendmail(EMAIL_SENDER, email_recipients, msg.as_string())

        logging.info(f"Subject: {subject} | Sending to: {email_recipients}")

        # 🔔 Send SMS notifications as plain text
        for sms_email in sms_recipients:
            sms_msg = MIMEText(sms_message)
            sms_msg["From"] = EMAIL_SENDER
            sms_msg["To"] = sms_email
            sms_msg["Subject"] = ""
            server.sendmail(EMAIL_SENDER, [sms_email], sms_msg.as_string())


def run_monitor():
    if DEBUG_MODE:
        logging.debug("Starting monitor run...")
    grouped_results = {}
    group_sms_mapping = {}


    for key, config in TARGETS.items():
        try:
            url = config["url"]
            keyword = config["keyword"]
            keyword2 = config.get("keyword2")
            keyword3 = config.get("keyword3")
            description = config["description"]
            fmt = config["format"]
            email_group = config.get("email_group", "students")
            sms_group = config.get("sms_group","sms")            
            

            if DEBUG_MODE:
                logging.debug(f"Checking target: {description} ({fmt})")

            result = None
            if fmt == "pdf":
                result = download_pdf_and_search(url, keyword, f"{key}.pdf", keyword2, keyword3)
            elif fmt == "html":
                result = search_html(url, keyword)
            elif fmt == "html_table_row":
                result = search_waitlist_row(url, keyword)

            if result:
                snapshot_key = key
                snapshot_data = {
                    "description": description,
                    "url": url,
                    "matched": result
                }

                if has_changed(snapshot_key, snapshot_data) or FORCE_MODE:
                    grouped_results.setdefault(email_group, []).append(snapshot_data)
                    if sms_group:
                        group_sms_mapping[email_group] = EMAIL_GROUPS.get(sms_group, [])

        except Exception as e:
            logging.error(f"Error processing {config['description']}: {e}")
            if EMAIL_GROUPS.get("admins"):
                send_email_html(
                    subject=f"Error in {description}",
                    results=[{"description": description, "url": url, "matched": f"ERROR: {e}"}],
                    email_recipients=EMAIL_GROUPS["admins"],
                    sms_recipients=[]
                )

    for group, results in grouped_results.items():
        if group in EMAIL_GROUPS:
            sms_recipients = group_sms_mapping.get(group, [])
            send_email_html(
                subject=f"Med-P Waiting List Update Report – {group}",
                results=results,
                email_recipients=EMAIL_GROUPS[group],
                sms_recipients=sms_recipients
            )
        else:
            logging.warning(f"Group '{group}' not found in EMAIL_GROUPS, skipping email.")

if __name__ == "__main__":
    run_monitor()




