import json
import os
import re
import time

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from flask import Flask
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver import Chrome
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

load_dotenv()

# Define globals
USERNAME: str = os.getenv("PSUT_USERNAME", "")
PASSWORD: str = os.getenv("PSUT_PASSWORD", "")
IS_RUNNING_IN_DOCKER: bool = True

# Define flask app
app = Flask(__name__)


def close_notifications(browser):
    """Close the notification box if it exists"""
    try:
        notification_close = browser.find_element(
            by="xpath", value="/html/body/div[3]/div/div[5]/div/div/div[1]/button/span"
        )
        time.sleep(1)
        notification_close.click()
    except NoSuchElementException:
        print("No notification close button found, continuing...")


def scrape_lectures(browser: Chrome):
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

    lectures_data: list[dict] = []
    try:
        # Loop through them and open each one
        for lecture in lectures:
            link = lecture.find_element(By.TAG_NAME, "a")
            # Get the link href
            href = link.get_attribute("href")
            # Open the link in a new tab
            browser.execute_script("window.open(arguments[0]);", href)

            # Switch to the new tab
            browser.switch_to.window(browser.window_handles[-1])

            # Extract all relevant data
            title = wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, "/html/body/div[2]/div/div[1]/div/div[1]/h4/span[1]")
                )
            ).text
            # The browser inserts the word 'Posted' so ill remove it
            title = title.replace("Posted", "").strip()

            #############################################
            with open("temp.txt", "w", encoding="utf-8") as f:
                f.write(browser.page_source)
            #############################################

            soup = BeautifulSoup(browser.page_source, "lxml")

            # Date and time
            date_and_time = soup.find_all(
                "span", class_="col-auto text-muted font-small-3 d-inline-block"
            )
            if len(date_and_time) != 2:
                raise ValueError("Could not find date and time spans.")

            date = date_and_time[0].text.strip()
            time_ = date_and_time[1].text.strip()

            # Info card
            info_card = soup.find("div", id="info-details")

            # Activity Hours
            activity_hours = info_card.find(
                "span", string=lambda text: "Activity Hours" in text
            )
            if activity_hours:
                activity_hours = activity_hours.parent.text.replace(
                    "Activity Hours:", ""
                ).strip()
            else:
                activity_hours = None

            # Restrictions
            restrictions = info_card.find(
                "strong", string=lambda text: "Registration Conditions" in text
            )
            if restrictions:
                restrictions = restrictions.find_next(
                    "div", class_="form-group"
                ).text.strip()
                restrictions = re.sub(r"\s+", " ", restrictions).strip()
            else:
                restrictions = None

            # Maximum Registrations
            max_registrations = info_card.find(
                "span", string=lambda text: "Maximum Registration" in text
            )
            if max_registrations:
                max_registrations = max_registrations.parent.text.replace(
                    "Maximum Registration:", ""
                ).strip()
            else:
                max_registrations = None

            # Current registrations
            current_registrations = info_card.find(
                "span", string=lambda text: "Registered Count" in text
            )
            if current_registrations:
                current_registrations = current_registrations.parent.text.replace(
                    "Registered Count:", ""
                ).strip()
            else:
                current_registrations = None

            # Start and end date for registration
            dates = info_card.find(
                "label",
                string=lambda text: "Subscription and withdrawal Period" in text,
            )
            if dates:
                dates = dates.parent.text.replace(
                    "Subscription and withdrawal Period:", ""
                ).strip()
                dates = re.sub(r"\s+", " ", dates).strip()
                # Split into start and end date
                start_date, end_date = dates.split("-")
            else:
                start_date = None
                end_date = None

            # Activity officer and their email
            officer = info_card.find(
                "strong", string=lambda text: "Activity Officer" in text
            )
            if officer:
                officer_data = officer.parent.next_sibling.next_sibling
                officer_data = officer_data.find_all("div", class_="form-group")

                # Set these in case no info is found
                officer_name = None
                officer_email = None
                officer_phone = None

                for data in officer_data:
                    if "Name" in data.text:
                        officer_name = data.text.replace("Name:", "").strip()
                    elif "Email" in data.text:
                        officer_email = data.text.replace("Email:", "").strip()
                    elif "Mobile Number" in data.text:
                        officer_phone = data.text.replace("Mobile Number:", "").strip()
            else:
                officer_name = None
                officer_email = None
                officer_phone = None

            lectures_data.append(
                {
                    "title": title,
                    "date": date,
                    "time": time_,
                    "activity_hours": activity_hours,
                    "restrictions": restrictions,
                    "max_registrations": max_registrations,
                    "current_registrations": current_registrations,
                    "start_date": start_date,
                    "end_date": end_date,
                    "officer_name": officer_name,
                    "officer_email": officer_email,
                    "officer_phone": officer_phone,
                }
            )

            # Close the tab
            browser.close()

            # Switch back to the original window
            browser.switch_to.window(original_window)

        # Save to json
        with open("lectures.json", "w", encoding="utf-8") as j:
            json.dump(lectures_data, j, indent=2)

        print(f"{len(lectures_data)} activities saved to lectures.json")
        return "Scraping completed successfully.", 200

    except Exception as e:
        if IS_RUNNING_IN_DOCKER:
            return f"Error: {e}", 500
        else:
            print(f"An error occurred: {e}")

    finally:
        browser.quit()


def run_scraper():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    # I have to add these because headless without them doesnt work
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--start-maximized")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    # Path to chromium driver installed in Dockerfile
    if IS_RUNNING_IN_DOCKER:
        service = Service("/usr/bin/chromedriver")
    else:
        service = Service()

    browser = Chrome(service=service, options=options)

    scrape_lectures(browser)


if __name__ == "__main__":
    if not USERNAME or not PASSWORD:
        raise ValueError("Please set PSUT_USERNAME and PSUT_PASSWORD in the .env file.")

    run_scraper()
