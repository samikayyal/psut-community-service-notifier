import json
import os
from datetime import datetime

import requests
from dotenv import load_dotenv

from google_sheets import fetch_recipients_from_sheet

load_dotenv()


def generate_lecture_card(lec: dict) -> str:
    """Generate HTML card for a single lecture"""
    title = lec.get("title") or "Untitled Event"
    date = lec.get("date") or "Date not specified"

    if date != "Date not specified":
        try:
            date_obj = datetime.strptime(date, "%d/%m/%Y")
            day_name = date_obj.strftime("%A")
            date = f"{day_name}, {date}"
        except ValueError:
            pass

    time_val = lec.get("time") or "Time not specified"
    location = lec.get("location") or "Location not specified"
    activity_hours = lec.get("activity_hours")
    restrictions = lec.get("restrictions")
    max_reg = lec.get("max_registrations")
    current_reg = lec.get("current_registrations")
    start_date = lec.get("start_date")
    end_date = lec.get("end_date")
    officer_name = lec.get("officer_name")
    officer_email = lec.get("officer_email")
    officer_phone = lec.get("officer_phone")

    # Calculate registration status
    is_full = current_reg is not None and max_reg is not None and current_reg >= max_reg
    spots_left = max_reg - current_reg if max_reg and current_reg is not None else None
    status_color = "#2596be"
    status_text = (
        "FULL"
        if is_full
        else f"{spots_left} spots left" if spots_left is not None else "Available"
    )

    # Build officer contact section
    officer_section = ""
    if officer_name or officer_email or officer_phone:
        officer_details = []
        if officer_name:
            officer_details.append(f"<strong>{officer_name}</strong>")
        if officer_email:
            officer_details.append(
                f'<a href="mailto:{officer_email}" style="color: #1a73e8; text-decoration: none;">{officer_email}</a>'
            )
        if officer_phone:
            officer_details.append(
                f'<a href="tel:{officer_phone}" style="color: #1a73e8; text-decoration: none;">{officer_phone}</a>'
            )

        officer_section = f"""
        <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid #e0e0e0;">
            <div style="font-size: 12px; color: #666; margin-bottom: 4px;">📞 Contact Officer</div>
            <div style="font-size: 13px; color: #333;">{" • ".join(officer_details)}</div>
        </div>
        """
    else:
        officer_section = """
        <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid #e0e0e0;">
            <div style="font-size: 12px; color: #999; font-style: italic;">📞 Contact information not available</div>
        </div>
        """

    # Build restrictions section
    restrictions_section = ""
    if restrictions:
        restrictions_section = f"""
        <div style="background: #fff3cd; padding: 8px 12px; border-radius: 6px; margin-top: 10px; font-size: 12px; color: #856404;">
            ⚠️ {restrictions}
        </div>
        """

    # Activity hours badge - highlight if 0 hours
    hours_badge = ""
    is_zero_hours = activity_hours is not None and str(activity_hours) == "0"
    if activity_hours is not None:
        if is_zero_hours:
            hours_badge = """
            <span style="background: #ff6b6b; color: #ffffff; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; animation: pulse 1s infinite;">
                ⚠️ 0 Service Hours
            </span>
            """
        else:
            hours_badge = f"""
            <span style="background: #e3f2fd; color: #1565c0; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: 600;">
                {activity_hours} Service Hour{"s" if activity_hours != "1" else ""}
            </span>
            """

    # Registration deadline section
    registration_deadline = ""
    if start_date or end_date:
        deadline_parts = []
        if start_date:
            deadline_parts.append(f"Opens: {start_date}")
        if end_date:
            deadline_parts.append(f"Closes: {end_date}")
        registration_deadline = f"""
        <div style="font-size: 12px; color: #666; margin-top: 8px;">
            🗓️ Registration: {" | ".join(deadline_parts)}
        </div>
        """

    # Card border styling - highlight if 0 hours
    card_border = "3px solid #ff6b6b" if is_zero_hours else "1px solid #e8e8e8"
    card_shadow = (
        "0 4px 16px rgba(255,107,107,0.4)"
        if is_zero_hours
        else "0 2px 8px rgba(0,0,0,0.1)"
    )

    return f"""
    <div style="background: #ffffff; border-radius: 12px; box-shadow: {card_shadow}; margin-bottom: 20px; overflow: hidden; border: {card_border};">
        <!-- Status Banner -->
        <div style="background: {status_color}; color: white; padding: 6px 16px; font-size: 12px; font-weight: 600; text-align: right;">
            {status_text} ({current_reg or 0}/{max_reg or "?"})
        </div>
        
        <!-- Card Content -->
        <div style="padding: 20px;">
            <!-- Title and Hours -->
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px;">
                <h3 style="margin: 0; color: #1a1a1a; font-size: 18px; font-weight: 600; line-height: 1.4;">{title}</h3>
            </div>
            <div style="margin-bottom: 12px;">{hours_badge}</div>
            
            <!-- Event Details Grid -->
            <div style="background: #f8f9fa; border-radius: 8px; padding: 14px;">
                <div style="margin-bottom: 10px;">
                    <div style="font-size: 12px; color: #666; margin-bottom: 2px;">📅 Date & Time</div>
                    <div style="font-size: 14px; color: #333; font-weight: 500;">{date} • {time_val}</div>
                </div>
                <div>
                    <div style="font-size: 12px; color: #666; margin-bottom: 2px;">📍 Location</div>
                    <div style="font-size: 14px; color: #333; font-weight: 500;">{location}</div>
                </div>
            </div>
            
            {registration_deadline}
            {restrictions_section}
            {officer_section}
        </div>
    </div>
    """


def send_brevo_email(lectures: list[dict]) -> tuple[str, bool]:
    """Formats lecture data and sends via Brevo
    returns: Message indicating success or failure, and a bool success flag
    """
    api_key = os.getenv("BREVO_API_KEY")
    sender_email = os.getenv("SENDER_EMAIL")

    # Fetch recipients from Google Sheet
    try:
        recipients = fetch_recipients_from_sheet()
    except Exception as e:
        return f"Failed to fetch recipients from Google Sheet: {e}", False

    if not api_key or not sender_email:
        return "Brevo configuration missing in .env", False
    if not recipients:
        return "No recipients found in Google Sheet", False

    # 1. Generate lecture cards
    lecture_cards = ""
    for lec in lectures:
        lecture_cards += generate_lecture_card(lec)

    email_body = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f0f2f5;">
        <!-- Email Container -->
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            
            <!-- Cards Container -->
            <div style="background: #f0f2f5; padding: 20px; border-radius: 16px;">
                {lecture_cards}
            </div>
            
            <!-- Footer -->
            <div style="text-align: center; padding: 20px; color: #888; font-size: 12px;">
                <p style="margin: 0;">This is an automated notification from PSUT Community Service Notifier</p>
                <p style="margin: 8px 0 0 0;">Register quickly as spots fill up fast! 🚀</p>
            </div>
            
        </div>
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
