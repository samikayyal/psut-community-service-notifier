import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()


def send_brevo_email(lectures: list[dict]) -> tuple[str, bool]:
    """Formats lecture data and sends via Brevo
    returns: Message indicating success or failure, and a bool success flag
    """
    api_key = os.getenv("BREVO_API_KEY")
    sender_email = os.getenv("SENDER_EMAIL")
    # emails are comma-separated in recipients.txt
    with open("recipients.txt", "r") as f:
        recipients_str = f.read().strip()

    recipients = [email.strip() for email in recipients_str.split(",") if email.strip()]
    if not api_key or not sender_email:
        return "Brevo configuration missing in .env", False
    if not recipients:
        return "No recipients found in recipients.txt", False

    # 1. Format Data into HTML
    html_rows = ""
    for lec in lectures:
        # Handle None values safely
        title = lec.get("title") or "N/A"
        date = lec.get("date") or "N/A"
        time_val = lec.get("time") or "N/A"
        loc = lec.get("location") or "N/A"
        reg = f"{lec.get('current_registrations')}/{lec.get('max_registrations')}"

        html_rows += f"""
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd;">{title}</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{date} <br> {time_val}</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{loc}</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{reg}</td>
        </tr>
        """

    email_body = f"""
    <html>
    <body>
        <h2>New PSUT Lectures Found</h2>
        <table style="border-collapse: collapse; width: 100%;">
            <tr style="background-color: #f2f2f2;">
                <th style="padding: 8px; border: 1px solid #ddd; text-align: left;">Title</th>
                <th style="padding: 8px; border: 1px solid #ddd; text-align: left;">Time</th>
                <th style="padding: 8px; border: 1px solid #ddd; text-align: left;">Location</th>
                <th style="padding: 8px; border: 1px solid #ddd; text-align: left;">Registrations</th>
            </tr>
            {html_rows}
        </table>
    </body>
    </html>
    """

    # 2. Prepare Brevo Payload
    recipients = [{"email": email.strip()} for email in recipients if email.strip()]

    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json",
    }
    payload = {
        "sender": {"name": "Community Service", "email": sender_email},
        "to": recipients,
        "subject": f"PSUT Lectures Update: {len(lectures)} Found",
        "htmlContent": email_body,
    }

    # 3. Send
    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code in [200, 201]:
            return "Emails sent successfully via Brevo.", True
        else:
            return (
                f"Failed to send email via Brevo. Status: {response.status_code}, Response: {response.text}",
                False,
            )
    except Exception as e:
        return f"Exception occurred while sending email: {e}", False


if __name__ == "__main__":
    with open("lectures.json", "r") as f:
        lectures_data = json.load(f)

    message, success = send_brevo_email(lectures_data)
    print(message, success)
