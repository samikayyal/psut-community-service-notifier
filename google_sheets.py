import os
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials


def get_google_sheets_client() -> gspread.Client:
    """Initialize and return Google Sheets client using service account."""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
    ]

    # Check for credentials path from environment variable (Cloud Run Secret Manager)
    # or fall back to local file for development
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    if creds_path and Path(creds_path).exists():
        service_account_path = Path(creds_path)
    else:
        # Fall back to local file for development
        service_account_path = Path("avid-subject-479313-r6-e5902510883d.json")

    if not service_account_path.exists():
        raise FileNotFoundError(
            "Service account credentials not found. "
            "Set GOOGLE_APPLICATION_CREDENTIALS env var or place the JSON file locally."
        )

    credentials = Credentials.from_service_account_file(
        service_account_path, scopes=scopes
    )

    return gspread.authorize(credentials)


def fetch_recipients_from_sheet(
    sheet_id: str | None = None,
    sheet_name: str = "Form Responses 1",
    email_column: int = 2,
) -> list[str]:
    """
    Fetch email addresses from a Google Sheet.

    Args:
        sheet_id: The Google Sheet ID (from URL). If None, reads from GOOGLE_SHEET_ID env var.
        sheet_name: Name of the worksheet/tab (default: "Form Responses 1" for Google Forms).
        email_column: Column number containing emails (1-indexed, default: 2 for typical forms).

    Returns:
        List of email addresses.
    """
    if sheet_id is None:
        sheet_id = os.getenv("GOOGLE_SHEET_ID")

    if not sheet_id:
        raise ValueError(
            "Google Sheet ID not provided. Set GOOGLE_SHEET_ID in .env or pass sheet_id parameter."
        )

    client = get_google_sheets_client()

    try:
        spreadsheet = client.open_by_key(sheet_id)
        worksheet = spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        # Try to get the first worksheet if specified name not found
        worksheet = spreadsheet.get_worksheet(0)
    except gspread.SpreadsheetNotFound:
        raise ValueError(
            "Spreadsheet not found. Make sure the sheet is shared with the service account."
        )

    # Get all values from the email column (skip header row)
    all_values = worksheet.col_values(email_column)

    # Skip header and filter empty values
    emails = [
        email.strip().lower()  # type: ignore
        for email in all_values[1:]  # Skip header row
        if email and email.strip() and "@" in email  # type: ignore
    ]

    # Remove duplicates while preserving order
    seen = set()
    unique_emails = []
    for email in emails:
        if email not in seen:
            seen.add(email)
            unique_emails.append(email)

    return unique_emails


if __name__ == "__main__":
    # Test the function
    from dotenv import load_dotenv

    load_dotenv()

    try:
        recipients = fetch_recipients_from_sheet()
        print(f"Found {len(recipients)} recipients:")
        for email in recipients:
            print(f"  - {email}")
    except Exception as e:
        print(f"Error: {e}")
