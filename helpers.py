import json
import os
import re
import time

from bs4 import BeautifulSoup
from google.cloud import storage
from google.genai import errors
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from logger_setup import logger


def parse_gemini_error(e: errors.APIError) -> str:
    if e.code == 400:
        return "There is a typo, or a missing required field in your request."
    elif e.code == 403:
        return "PERMISSION_DENIED"
    elif e.code == 404:
        return "The requested resource was not found."
    elif e.code == 429:
        return "RESOURCE_EXHAUSTED: You have exceeded your quota limits."
    elif e.code >= 500:
        return "An internal server error occurred. Please try again later."
    else:
        return f"An unexpected error occurred: {e.message}"


def clean_html(content: str) -> str:
    # Remove href attributes
    content = re.sub(r'href="[^"]*"', 'href=""', content)
    # Remove src attributes
    content = re.sub(r'src="[^"]*"', 'src=""', content)

    # remove script tags and their content
    content = re.sub(r"<script.*?>.*?</script>", "", content, flags=re.DOTALL)

    # Style tags and their content
    content = re.sub(r"<style.*?>.*?</style>", "", content, flags=re.DOTALL)
    soup = BeautifulSoup(content, "lxml")

    return soup.prettify()


def get_gcs_bucket() -> storage.Bucket | None:
    """Get the GCS bucket object"""
    # If running locally without GCS configured, this might fail if credentials aren't set up.
    # We'll assume the environment is configured correctly for Cloud Run.
    try:
        if os.path.exists("avid-subject-479313-r6-e5902510883d.json"):
            client = storage.Client.from_service_account_json(
                "avid-subject-479313-r6-e5902510883d.json"
            )
        else:
            client = storage.Client()
        bucket_name = os.getenv("GCS_BUCKET_NAME")
        if not bucket_name:
            logger.warning("GCS_BUCKET_NAME not set. Persistence disabled.")
            return None
        return client.bucket(bucket_name)
    except Exception as e:
        logger.warning(f"Failed to initialize GCS client: {e}")
        return None


def load_previous_lectures() -> list[dict]:
    """Load previously scraped lectures from GCS"""
    try:
        bucket = get_gcs_bucket()
        if not bucket:
            return []
        blob = bucket.blob("lectures_data.json")
        if blob.exists():
            data = blob.download_as_text()
            return json.loads(data)
    except Exception as e:
        logger.warning(f"Could not load previous lectures from GCS: {e}")
    return []


def save_lectures_to_gcs(lectures: list[dict]):
    """Save current lectures to GCS"""
    try:
        bucket = get_gcs_bucket()
        if not bucket:
            return
        blob = bucket.blob("lectures_data.json")
        blob.upload_from_string(
            json.dumps(lectures, indent=2), content_type="application/json"
        )
        logger.info("Saved lectures to GCS")
    except Exception as e:
        logger.error(f"Could not save lectures to GCS: {e}")


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
    except TimeoutException:
        logger.info("No notification close button found within timeout, continuing...")
