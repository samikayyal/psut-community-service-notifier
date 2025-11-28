from google.genai import errors
import re
from bs4 import BeautifulSoup

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