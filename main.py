import json
import logging
import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver import Chrome
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from helpers import clean_html, parse_gemini_error

load_dotenv()

# Define globals
USERNAME: str = os.getenv("PSUT_USERNAME", "")
PASSWORD: str = os.getenv("PSUT_PASSWORD", "")
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


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


def close_notifications(browser):
    """Close the notification box if it exists"""
    try:
        notification_close = WebDriverWait(browser, 5).until(
            EC.presence_of_element_located(
                (By.XPATH, "/html/body/div[3]/div/div[5]/div/div/div[1]/button/span")
            )
        )

        time.sleep(1)
        notification_close.click()
    except NoSuchElementException:
        logger.info("No notification close button found, continuing...")


def scrape_lectures(
    browser: Chrome, model_name: str, system_prompt: str = ""
) -> list[dict]:
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

    # find the community service lectures
    div = wait.until(EC.presence_of_element_located((By.ID, "cCarousel")))
    lectures = div.find_elements(By.TAG_NAME, "article")

    original_window = browser.current_window_handle

    # Collect all hrefs first to avoid stale element issues
    lecture_hrefs = []
    for lecture in lectures:
        try:
            link = lecture.find_element(By.TAG_NAME, "a")
            href = link.get_attribute("href")
            if href:
                lecture_hrefs.append(href)
        except Exception as e:
            logger.warning(f"Could not get href from lecture: {e}")

    lectures_data: list[dict] = []
    lectures_html_pages: list[str] = []
    # Collect html content of each lecture
    try:
        for href in lecture_hrefs:
            # Open the link in a new tab
            browser.execute_script("window.open(arguments[0]);", href)

            # Switch to the new tab
            browser.switch_to.window(browser.window_handles[-1])
            time.sleep(5)  # Wait for the page to load
            page_content = clean_html(browser.page_source)
            # Get the data needed from Gemini:
            lectures_html_pages.append(page_content)

            # Close the tab if we're not on the original window
            if browser.current_window_handle != original_window:
                browser.close()
            # Switch back to the original window
            browser.switch_to.window(original_window)
            # Small delay to let the browser stabilize
            time.sleep(0.5)

        # Split the pages into 2 batches to avoid token limits
        batch_size = len(lectures_html_pages) // 2 + 1
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
                    The information you have to extract is: title, date, time, location, activity_hours, restrictions, max_registrations, current_registrations, start_date, end_date, officer_name, officer_email, officer_phone.
                    Here are the HTML pages:

                    {combined_pages}"""
                    ],
                )
                data = response.model_dump_json()
                batch_data = json.loads(data)
                lectures_data.extend(batch_data)
                logger.info(f"Processed batch of {len(batch_data)} lectures")

            except errors.APIError as e:
                raise Exception(f"Gemini API Error: {parse_gemini_error(e)}")

            # Parse the response and add to lectures_data

        logger.info(f"Scraped {len(lectures_data)} lectures")
        return lectures_data
    except Exception as e:
        logger.error(f"An error occurred while collecting lecture information: {e}")
        raise


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

        if os.getenv("IS_DOCKER"):
            options.binary_location = "/usr/bin/chromium"
            service = Service(executable_path="/usr/bin/chromedriver")

        browser = Chrome(service=service, options=options)
    except Exception as e:
        logger.error(f"Failed to initialize the browser: {e}")
        return None

    # =========== Create gemini client ===========
    try:
        model_name = "gemini-2.5-flash"
        system_prompt = """
        You are a high-precision HTML scraping agent. Your goal is to extract structured data from raw HTML code.

        Rules:
        1. If a field is not found, set the value to null.
        2. Preserve all Arabic text exactly as it appears. Do not translate Arabic to English.
        3. You will receive multiple HTML pages separated by the delimiter: "<<<NEXT_PAGE_SEPARATOR>>>".
        4. Process every page provided and return one JSON object per page in the list.
        5. Adhere STRICTLY to the provided schema. Do not add any extra fields or information."""

    except Exception as e:
        logger.error(f"Failed to initialize Gemini client: {e}")
        browser.quit()
        return None

    # =========== Run the scraper ===========
    try:
        data = scrape_lectures(browser, model_name, system_prompt)
        return data
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        return None
    finally:
        browser.quit()


def main():
    # =========== Run the scraper ===========
    data = run_scraper()
    if not data:
        logger.error("No data scraped.")
        return

    # =========== Send emails ===========


if __name__ == "__main__":
    main()
