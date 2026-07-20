from __future__ import annotations

import csv
import os
import sys
from http.client import REQUEST_TIMEOUT
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

#Config
LOGIN_PAGE_URL = "https://example.com/login"
LOGIN_POST_URL = "https://example.com/login"
PROTECTED_PAGE_URL = "https://example.com/protected-page"

OUTPUT_DIRECTORY = Path("output")
OUTPUT_FILE = OUTPUT_DIRECTORY / "scraped_data.csv"

#Exceptions
class ScraperError(Exception):
    """Base exception for scraper errors"""

class LoginError(ScraperError):
    """Raised when login fails"""

class ParsingError(ScraperError):
    """Raised when parsing fails"""

#Credentials
def load_credentials() -> tuple[str, str]:
    """
    Load the username and password from the environment variables.

    During local development, load_dotenv() reads values from .env.
    In Power Automate, these values can instead be supplied through
    enviornment variables or flow inputs.
    """
    load_dotenv()

    username = os.getenv("SCRAPER_USERNAME")
    password = os.getenv("SCRAPER_PASSWORD")

    if not username or not password:
        raise ScraperError("SCRAPER_USERNAME and SCRAPER_PASSWORD are required")

    return username, password

#Login
def get_hidden_form_fields(html: str) -> dict[str, str]:
    """
    Extract hidden form fields from HTML.

    This helps preserve CSRF tokens and other hidden values that the
    server expects during login.
    """
    soup = BeautifulSoup(html, "html.parser")

    login_form = soup.select_one("form")

    if login_form is None:
        raise ParsingError("Could not find the login form")

    hidden_fields: dict[str, str] = {}

    for input_element in login_form.select('input[type="hidden"]'):
        field_name = input_element.get("name")
        field_value = input_element.get("value", "")

        if field_name:
            hidden_fields[field_name] = field_value

        return hidden_fields

def log_in(
        session: requests.Session,
        username: str,
        password: str,
) -> None:
    """
    Open the login page and submit the authentication form.
    """
    login_page_response = session.get(
        LOGIN_PAGE_URL,
        timeout=REQUEST_TIMEOUT,
    )
    login_page_response.raise_for_status()

    form_data = get_hidden_form_fields(login_page_response.text)

    #Change these field names to match the website's form.
    form_data.update(
        {
            "username": username,
            "password": password,
        }
    )

    login_response = session.post(
        LOGIN_POST_URL,
        data=form_data,
        timeout=REQUEST_TIMEOUT,
        allow_redirects=True,
    )
    login_response.raise_for_status()

    verify_login(login_response)

def verify_login(response: requests.Response) -> None:
    """
    Verify authentication using characteristics of the logged-in page.

    Replace these checks with something reliable from the actual site.
    """
    page_text = response.text.lower()
    final_url = response.url.lower()

    still_on_login_page = "/login" in final_url
    login_error_present = "invalid username or password" in page_text

    if still_on_login_page or login_error_present:
        raise LoginError("Login failed")

#Protected page
def fetch_protected_page(session: requests.Session) -> str:
    """
    Request the protected page and return the authenticated.
    """
    response = session.get(
        PROTECTED_PAGE_URL,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()

    if "/login" in response.url.lower():
        raise LoginError("Redirected to the login page.")

    return response.text

#Data extraction
def parse_records(html: str) -> list[dict[str, Any]]:
    """
    Extract records from an HTML table.

    Adjust the selectors and column assignments to match the website.
    """
    soup = BeautifulSoup(html, "html.parser")

    table = soup.select_one("table")

    if table is None:
        raise ParsingError(
            "Could not find table#customer-table on the protected page."
        )

    records: list[dict[str, Any]] = []

    for row in table.select("tbody tr"):
        cells = row.select("td")

        if len(cells) < 3:
            continue

        record = {
            "name": cells[0].get_text(strip=True),
            "email": cells[1].get_text(strip=True),
            "status": cells[2].get_text(strip=True),
        }

        records.append(record)

    if not records:
        raise ParsingError("No records found in the table.")

    return records

#CSV
def save_to_csv(
        records: list[dict[str, Any]],
        output_path: Path,
) -> None:
    """
    Save the extracted records as UTF-8 CSV.
    """
    if not records:
        raise ScraperError("No records to save")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = list(records[0].keys())

    with output_path.open(
        mode="w",
        newline="",
        encoding="utf-8-sig",
    ) as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(records)

#Main
def run() -> Path:
    """
    Run the complete scraping workflow and return the output path.
    """
    username, password = load_credentials()

    with requests.Session() as session:
        session.headers.update(
            {
                "User-Agent": (
                    "AuthorizedInternalDataCollector/1.0"
                )
            }
        )
        log_in(session, username, password)

        protected_html = fetch_protected_page(session)

        records = parse_records(protected_html)

        save_to_csv(records, OUTPUT_FILE)

    return OUTPUT_FILE.resolve()

def main() -> int:
    """
    Command-line entry point.

    Exit code 0 means success, non-zero means failure.
    """
    try:
        output_path = run()

        #A stable, machine-readable result is helpful for Power Automate.
        print(f"STATUS=SUCCESS")
        print(f"OUTPUT_PATH={output_path}")

        return 0

    except requests.RequestException as error:
        print(f"STATUS=ERROR", file=sys.stderr)
        print(f"ERROR_TYPE=SCRAPER", file=sys.stderr)
        print(f"ERROR_MESSAGE={error}", file=sys.stderr)

        return 1

    except Exception as error:
        print(f"STATUS=ERROR", file=sys.stderr)
        print(f"ERROR_TYPE=SCRAPER", file=sys.stderr)
        print(f"ERROR_MESSAGE={error}", file=sys.stderr)

        return 1

if __name__ == "__main__":
    raise SystemExit(main())