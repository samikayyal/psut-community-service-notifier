import json
import os
import time
import traceback
from datetime import datetime

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from flask import Flask, jsonify
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field
from selenium.webdriver import Chrome
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import logger_setup
from helpers import (
    clean_html,
    close_notifications,
    load_previous_lectures,
    parse_gemini_error,
    save_lectures_to_gcs,
)
from send_emails import send_brevo_email

load_dotenv()
# Define globals
USERNAME: str = os.getenv("PSUT_USERNAME", "")
PASSWORD: str = os.getenv("PSUT_PASSWORD", "")
logger = logger_setup.logger
app = Flask(__name__)


class LectureData(BaseModel):
    title: str | None = Field(description="Title of the lecture")
    date: str | None = Field(description="Date of the lecture")
    time: str | None = Field(description="Time of the lecture")
    location: str | None = Field(description="Location of the lecture")
    activity_hours: str | None = Field(
        description="Number of activity hours, marked under Activity Hours"
    )
    restrictions: str | None = Field(
        description="Any restrictions for the lecture, marked by Registration Conditions"
    )
    max_registrations: int | None = Field(
        description="Maximum number of registrations allowed, marked under Maximum Registration"
    )
    current_registrations: int | None = Field(
        description="Current number of registrations, marked under Registered Count:"
    )
    start_date: str | None = Field(
        description="Start date for registration, marked under Subscription and withdrawal Period"
    )
    end_date: str | None = Field(
        description="End date for registration, marked under Subscription and withdrawal Period"
    )
    officer_name: str | None = Field(
        description="Name of the officer in charge, marked under Activity Officer"
    )
    officer_email: str | None = Field(
        description="Email of the officer in charge, marked under Activity Officer"
    )
    officer_phone: str | None = Field(
        description="Phone number of the officer in charge, marked under Activity Officer"
    )
    href: str | None = Field(description="The source URL of the lecture page")


def scrape_lectures(
    browser: Chrome, model_name: str, system_prompt: str, lecture_hrefs: list[str]
) -> list[dict]:
    lectures_html_pages = []
    lectures_data = []
    original_window = browser.current_window_handle
    try:
        for href in lecture_hrefs:
            # Open the link in a new tab
            browser.execute_script("window.open(arguments[0]);", href)

            # Switch to the new tab
            browser.switch_to.window(browser.window_handles[-1])
            # Wait for the page to load - wait for body first, then the dynamic element
            WebDriverWait(browser, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            # Small delay to allow JavaScript to initialize dynamic content
            time.sleep(1)

            page_content = clean_html(browser.page_source)
            # Add the href to the page content so Gemini can extract it
            page_content_with_href = f"Source URL: {href}\n{page_content}"
            # Get the data needed from Gemini:
            lectures_html_pages.append(page_content_with_href)

            # Close the tab if we're not on the original window
            if browser.current_window_handle != original_window:
                browser.close()
            # Switch back to the original window
            browser.switch_to.window(original_window)
            # Small delay to let the browser stabilize
            time.sleep(0.5)

        # Split the pages into batches to avoid token limits
        # Use a minimum batch size of 5, or all pages if fewer than 5
        batch_size = max(5, (len(lectures_html_pages) + 1) // 2)
        for i in range(0, len(lectures_html_pages), batch_size):
            batch_pages = lectures_html_pages[i : i + batch_size]
            combined_pages = "\n\n<<<NEXT_PAGE_SEPARATOR>>>\n\n".join(batch_pages)

            try:
                client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))
                response = client.models.generate_content(
                    model=model_name,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        thinking_config=types.ThinkingConfig(thinking_budget=0),
                        response_mime_type="application/json",
                        response_schema=list[LectureData],
                    ),
                    contents=[
                        f"""
                    Extract all information from the html pages mentioned in the schema, adhere to it STRICTLY.
                    The information you have to extract is: title, date, time, location, activity_hours, restrictions, max_registrations, current_registrations, start_date, end_date, officer_name, officer_email, officer_phone, href.
                    Note: The href (Source URL) is provided at the top of each page content.
                    Here are the HTML pages:

                    {combined_pages}"""
                    ],
                )
                if response.text is None:
                    raise Exception("Gemini API returned no text in the response.")
                batch_data = json.loads(response.text)
                lectures_data.extend(batch_data)
                logger.info(f"Processed batch of {len(batch_data)} lectures")

            except errors.APIError as e:
                raise Exception(f"Gemini API Error: {parse_gemini_error(e)}")

            # Parse the response and add to lectures_data

        logger.info(f"Done Scraping {len(lectures_data)} lectures")
        return lectures_data
    except Exception as e:
        logger.error(f"An error occurred while collecting lecture information: {e}")
        # print the stack trace for debugging

        traceback.print_exc()
        raise


def scrape_hrefs(browser: Chrome) -> list[str]:
    browser.get("https://portal.psut.edu.jo")

    # Define wait object
    wait = WebDriverWait(browser, 10)

    # Login
    username_input = wait.until(EC.presence_of_element_located((By.ID, "UserID")))
    password_input = browser.find_element(By.ID, "loginPass")

    username_input.send_keys(USERNAME)
    password_input.send_keys(PASSWORD)

    password_input.submit()

    close_notifications(browser)

    # Change language to English
    dropdown = wait.until(EC.presence_of_element_located((By.ID, "dropdown-flag")))
    dropdown.click()
    english_option = wait.until(
        EC.presence_of_element_located(
            (By.XPATH, '//*[@id="navbar-mobile"]/ul[2]/li[2]/div/a[2]')
        )
    )
    english_option.click()

    # I have to close the noti box again
    close_notifications(browser)

    # go to the lectures page
    # Find activites card and click it
    activities_card = WebDriverWait(browser, 10).until(
        EC.presence_of_element_located(
            (
                By.CSS_SELECTOR,
                "body > div.app-content.content > div > div:nth-child(3) > div > div > div > div > a:nth-child(3)",
            )
        )
    )
    activities_card.click()

    # switch to the new tab
    browser.switch_to.window(browser.window_handles[-1])

    # Wait for the activites timeline to load
    WebDriverWait(browser, 10).until(
        EC.presence_of_element_located((By.CLASS_NAME, "events"))
    )

    # Loop through available dates and get lectures with minimum date today
    timeline_div = browser.find_element(By.CLASS_NAME, "events")
    list_items = timeline_div.find_elements(By.TAG_NAME, "li")

    lecture_hrefs: list[str] = []

    for li in list_items:
        anchor = li.find_element(By.TAG_NAME, "a")
        date = anchor.get_attribute("data-date") or "10/10/1970"
        date_obj = datetime.strptime(date, "%d/%m/%Y").date()

        # Only click if today or in the future
        if date_obj < datetime.now().date():
            continue

        # Dont click if its selected (get from class)
        if "selected" not in (anchor.get_attribute("class") or ""):
            # use JavaScript click to avoid ElementNotInteractableException
            browser.execute_script("arguments[0].click();", anchor)

        content_div = WebDriverWait(browser, 10).until(
            EC.presence_of_element_located((By.ID, "event-content"))
        )

        # Another wait to make sure card is loaded
        WebDriverWait(content_div, 10).until(
            EC.visibility_of_element_located((By.CLASS_NAME, "card"))
        )

        # Could be multiple lectures on the same day
        mini_soup = BeautifulSoup(content_div.get_attribute("innerHTML"), "lxml")
        lecture_titles = mini_soup.find_all("h4", class_="card-title")
        for title in lecture_titles:
            anchor = title.find("a")
            if anchor and anchor.has_attr("href"):
                lecture_hrefs.append(anchor["href"])

    return lecture_hrefs


def run_scraper() -> list[dict] | None:
    if not USERNAME or not PASSWORD:
        raise ValueError("Please set PSUT_USERNAME and PSUT_PASSWORD in the .env file.")

    # =========== Create the browser ===========
    try:
        options = Options()
        options.add_argument("--headless=new")
        # I have to add these because headless without them doesnt work
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--start-maximized")
        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        # Additions for Docker/Cloud Run
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")

        service = Service()

        if os.getenv("IS_DOCKER", "").lower() == "true":
            options.binary_location = "/usr/bin/chromium"
            service = Service(executable_path="/usr/bin/chromedriver")

        browser = Chrome(service=service, options=options)
    except Exception as e:
        logger.error(f"Failed to initialize the browser: {e}")
        return None

    # =========== Prompt and model details ===========

    model_name = "gemini-2.5-flash"
    system_prompt = """
    You are a high-precision HTML scraping agent. Your goal is to extract structured data from raw HTML code.

    Rules:
    1. If a field is not found, set the value to null.
    2. Preserve all Arabic text exactly as it appears. Do not translate Arabic to English.
    3. You will receive multiple HTML pages separated by the delimiter: "<<<NEXT_PAGE_SEPARATOR>>>".
    4. Process every page provided and return one JSON object per page in the list.
    5. Adhere STRICTLY to the provided schema. Do not add any extra fields or information."""

    # =========== Run the scraper ===========
    try:
        hrefs = scrape_hrefs(browser)
        logger.info(f"Found {len(hrefs)} lecture links to scrape.")
        data = scrape_lectures(browser, model_name, system_prompt, hrefs)
        return data
    except Exception as e:
        logger.error(f"An error occurred: {e}:\n\n{traceback.format_exc()}")
        return None
    finally:
        browser.quit()


@app.route("/", methods=["GET", "POST"])
def main():
    logger.info("Starting scraper process...")
    # =========== Run the scraper ===========
    current_lectures = run_scraper()
    if not os.getenv("IS_DOCKER", "").lower() == "true":
        logger.info(f"Scraped these: {current_lectures}")
    if current_lectures is None:
        logger.error("Scraper failed to run.")
        return jsonify({"error": "Scraper failed to run."}), 500

    if not current_lectures:
        logger.info("No lectures found on the portal.")
        return jsonify({"message": "No lectures found on the portal."}), 200

    # =========== Check for new lectures ===========
    previous_lectures = load_previous_lectures()

    # Create a unique key for previous lectures
    # We use href as the unique identifier
    prev_keys = {lecture.get("href") for lecture in previous_lectures}

    new_lectures = []
    for lecture in current_lectures:
        key = lecture.get("href")
        if key not in prev_keys:
            new_lectures.append(lecture)

    if not new_lectures:
        logger.info("No new lectures found.")
        return jsonify({"message": "No new lectures found."}), 200

    logger.info(f"Found {len(new_lectures)} new lectures.")

    # Save them locally if not running in docker
    if not os.getenv("IS_DOCKER", "").lower() == "true":
        with open("lectures.json", "w", encoding="utf-8") as f:
            json.dump(new_lectures, f, ensure_ascii=False, indent=4)

    # =========== Send emails ===========
    message, success = send_brevo_email(new_lectures)
    if success:
        logger.info("Emails sent successfully.")
        # Only save the new state if emails were sent successfully
        # This ensures that if email sending fails, we'll try again next time
        save_lectures_to_gcs(previous_lectures + new_lectures)
        return jsonify({"message": message}), 200
    else:
        logger.error(f"Failed to send emails: {message}")
        return jsonify({"error": message}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
