"""PhilGEPS scraper and data source.

Uses httpx + selectolax for lightweight scraping of the ASP.NET WebForms site.
No browser required — postback state is managed manually.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Any

import httpx
from selectolax.parser import HTMLParser

logger = logging.getLogger(__name__)

PHILGEPS_BASE = "https://notices.philgeps.gov.ph"
SEARCH_URL = f"{PHILGEPS_BASE}/GEPSNONPILOT/Tender/SplashOpportunitiesSearchUI.aspx?menuIndex=3"
PRINTABLE_URL = f"{PHILGEPS_BASE}/GEPSNONPILOT/Tender/PrintableBidNoticeAbstractUI.aspx?refid="

# Rate limiting: delay between requests (seconds)
REQUEST_DELAY = 1.0
_last_request_time = 0.0

# Retry config
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0  # exponential base

# Shared client for connection reuse
_client: httpx.Client | None = None


def _get_client() -> httpx.Client:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.Client(
            timeout=30,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
    return _client


def close() -> None:
    """Close browser/session resources."""
    global _client
    if _client and not _client.is_closed:
        _client.close()
        _client = None


def _rate_limit() -> None:
    """Enforce minimum delay between requests."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < REQUEST_DELAY:
        time.sleep(REQUEST_DELAY - elapsed)
    _last_request_time = time.time()


def _request_with_retry(method: str, url: str, **kwargs) -> httpx.Response:
    """Make an HTTP request with retry on transient failures."""
    client = _get_client()
    last_error = None

    for attempt in range(MAX_RETRIES):
        _rate_limit()
        try:
            if method == "GET":
                resp = client.get(url, **kwargs)
            else:
                resp = client.post(url, **kwargs)

            if resp.status_code == 503:  # PhilGEPS sometimes returns 503
                logger.warning(f"Got 503 on attempt {attempt + 1}, retrying...")
                time.sleep(RETRY_BACKOFF ** (attempt + 1))
                continue

            return resp

        except (httpx.TimeoutException, httpx.NetworkError) as e:
            last_error = e
            logger.warning(f"Request failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF ** (attempt + 1))

    raise httpx.HTTPError(f"Failed after {MAX_RETRIES} retries: {last_error}")


def _extract_viewstate(tree: HTMLParser) -> dict[str, str]:
    """Extract ASP.NET hidden form fields."""
    fields = {}
    for field_id in ("__VIEWSTATE", "__EVENTVALIDATION", "__VIEWSTATEGENERATOR"):
        el = tree.css_first(f"#{field_id}")
        if el:
            fields[field_id] = el.attributes.get("value", "")
    return fields


def _parse_date(text: str) -> str:
    """Normalize date strings from PhilGEPS.

    Handles formats like:
      - 'Jan 15, 2025'
      - 'January 15, 2025 10:00 AM'
      - '1/15/2025'
    Returns ISO-ish string or original text if parsing fails.
    """
    text = text.strip()
    if not text:
        return ""

    # Try common formats
    for fmt in (
        "%b %d, %Y %I:%M %p",
        "%B %d, %Y %I:%M %p",
        "%b %d, %Y",
        "%B %d, %Y",
        "%m/%d/%Y %I:%M %p",
        "%m/%d/%Y",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.strftime("%Y-%m-%d %H:%M") if "%H" in fmt or "%I" in fmt else dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return text


def _parse_search_results(html: str) -> tuple[list[dict[str, Any]], int]:
    """Parse search results from the flat table layout.

    PhilGEPS lays out all results in a single row with interleaved cells:
      [0] header link, [1] empty, [2-4] headers,
      then repeating groups of 4: [row_num, publish_date, closing_date, title_link]

    Returns (results, max_page) tuple.
    """
    tree = HTMLParser(html)
    results = []
    max_page = 1

    # Find the table containing refID links
    results_table = None
    for table in tree.css("table"):
        if table.css("a[href*='refID']"):
            results_table = table
            break

    if not results_table:
        return results, max_page

    # Parse pagination — look for page number links
    page_pattern = re.compile(r"numberPage_(\d+)")
    for link in tree.css("a[href*='numberPage']"):
        href = link.attributes.get("href", "")
        match = page_pattern.search(href)
        if match:
            page_num = int(match.group(1))
            max_page = max(max_page, page_num)

    # Get the data row (row index 2, after pagination rows)
    rows = results_table.css("tr")
    if len(rows) < 3:
        return results, max_page

    data_row = rows[2]
    cells = data_row.css("td")

    # Skip header cells (first 5), then parse groups of 4
    i = 5
    while i + 3 < len(cells):
        num_text = cells[i].text(strip=True)
        if not num_text.isdigit():
            i += 1
            continue

        publish_date = _parse_date(cells[i + 1].text(strip=True))
        closing_date = _parse_date(cells[i + 2].text(strip=True))

        # Extract title and category/agency from the cell
        link = cells[i + 3].css_first("a[href*='refID']")
        if not link:
            i += 4
            continue

        title = link.text(strip=True)
        href = link.attributes.get("href", "")

        ref_match = re.search(r"refID=(\d+)", href)
        ref_id = ref_match.group(1) if ref_match else ""

        # Category and agency are in a <span> with id containing "lblOrgAndBusCat"
        # Format: ", CATEGORY , AGENCY"
        category = ""
        agency = ""
        span = cells[i + 3].css_first("span[id*='lblOrgAndBusCat']")
        if span:
            span_text = span.text(strip=True)
            parts = span_text.split(" ,")
            if len(parts) >= 2:
                category = parts[0].lstrip(", ").strip()
                agency = parts[1].strip()
            elif len(parts) == 1:
                category = parts[0].lstrip(", ").strip()

        results.append({
            "ref_no": ref_id,
            "title": title,
            "agency": agency,
            "category": category,
            "abc": None,
            "mode": "",
            "area_of_delivery": "",
            "published_date": publish_date,
            "closing_date": closing_date,
            "description": "",
            "documents": "",
        })

        i += 4

    return results, max_page


def search(query: str, max_pages: int = 1) -> list[dict[str, Any]]:
    """Search PhilGEPS procurement notices.

    Args:
        query: Search keywords.
        max_pages: Number of pages to scrape (20 results/page).

    Returns:
        List of notice dicts.
    """
    all_results: list[dict[str, Any]] = []

    try:
        # Step 1: Get initial page
        r = _request_with_retry("GET", SEARCH_URL)
        if r.status_code != 200:
            logger.error(f"Initial page returned {r.status_code}")
            return all_results
        tree = HTMLParser(r.text)
        state = _extract_viewstate(tree)

        # Step 2: Activate Search tab
        r2 = _request_with_retry("POST", SEARCH_URL, data={
            **state,
            "__EVENTTARGET": "lbtnSearch",
            "__EVENTARGUMENT": "",
        })
        if r2.status_code != 200:
            logger.error(f"Search tab activation returned {r2.status_code}")
            return all_results
        tree2 = HTMLParser(r2.text)
        state2 = _extract_viewstate(tree2)

        # Step 3: Submit search (page 1)
        r3 = _request_with_retry("POST", SEARCH_URL, data={
            **state2,
            "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
            "txtKeyword": query,
            "btnSearch": "Search",
        })
        if r3.status_code != 200:
            logger.error(f"Search submission returned {r3.status_code}")
            return all_results

        results, max_page = _parse_search_results(r3.text)
        all_results.extend(results)

        logger.info(f"Page 1: {len(results)} results (max_page={max_page})")

        # Step 4: Navigate additional pages
        for page_num in range(2, min(max_pages + 1, max_page + 1)):
            tree3 = HTMLParser(r3.text)
            state3 = _extract_viewstate(tree3)

            r3 = _request_with_retry("POST", SEARCH_URL, data={
                **state3,
                "__EVENTTARGET": f"pgCtrlDetailedSearch$numberPage_{page_num}",
                "__EVENTARGUMENT": "",
            })
            if r3.status_code != 200:
                logger.warning(f"Page {page_num} returned {r3.status_code}, stopping")
                break

            page_results, _ = _parse_search_results(r3.text)
            if not page_results:
                logger.info(f"Page {page_num}: empty, stopping pagination")
                break

            # Deduplicate by ref_no
            existing_refs = {r["ref_no"] for r in all_results}
            new_results = [r for r in page_results if r["ref_no"] not in existing_refs]
            all_results.extend(new_results)
            logger.info(f"Page {page_num}: {len(page_results)} results ({len(new_results)} new)")

    except httpx.HTTPError as e:
        logger.error(f"HTTP error during search: {e}")

    return all_results


def get_notice_detail(ref_id: str) -> dict[str, Any]:
    """Fetch full details for a procurement notice.

    Args:
        ref_id: PhilGEPS reference number.

    Returns:
        Notice detail dict with ABC, description, contact, etc.
    """
    url = f"{PRINTABLE_URL}{ref_id}"

    try:
        r = _request_with_retry("GET", url)
        if r.status_code != 200:
            return {"ref_no": ref_id, "error": f"HTTP {r.status_code}"}

        return _parse_detail_page(r.text, ref_id)
    except httpx.HTTPError as e:
        return {"ref_no": ref_id, "error": str(e)}


def _parse_detail_page(html: str, ref_id: str) -> dict[str, Any]:
    """Parse a printable detail page."""
    tree = HTMLParser(html)

    detail: dict[str, Any] = {"ref_no": ref_id}

    # The printable page has key-value pairs in table cells
    labels_map = {
        "Procuring Entity": "agency",
        "Title": "title",
        "Area of Delivery": "area_of_delivery",
        "Solicitation Number": "solicitation_number",
        "Trade Agreement": "trade_agreement",
        "Procurement Mode": "mode",
        "Classification": "classification",
        "Category": "category",
        "Approved Budget for the Contract": "abc",
        "Delivery Period": "delivery_period",
        "Status": "status",
        "Date Published": "published_date",
        "Closing Date / Time": "closing_date",
        "Contact Person": "contact_person",
        "Fund Source": "fund_source",
        "Description": "_description_marker",
    }

    # Get all table cells
    cells = tree.css("td")
    for i, cell in enumerate(cells):
        text = cell.text(strip=True).rstrip(":")
        if text in labels_map and i + 1 < len(cells):
            key = labels_map[text]
            if key == "_description_marker":
                # Description content is further down
                for offset in (2, 1, 3):
                    if i + offset < len(cells):
                        content = cells[i + offset].text(strip=True)
                        if len(content) > 20:
                            detail["description"] = content
                            break
                continue

            value = cells[i + 1].text(strip=True)
            if key == "abc":
                value = _parse_php_amount(value)
            elif key in ("published_date", "closing_date"):
                value = _parse_date(value)
            detail[key] = value

    # Extract line items from description
    desc = detail.get("description", "")
    detail["line_items"] = _extract_line_items(desc)

    # Extract contact info
    contact = detail.get("contact_person", "")
    if contact:
        email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', contact)
        phone_match = re.search(r'63-\d+-\d+', contact)
        detail["contact_email"] = email_match.group(0) if email_match else ""
        detail["contact_phone"] = phone_match.group(0) if phone_match else ""

    return detail


def _extract_line_items(description: str) -> list[dict[str, Any]]:
    """Extract structured line items from description text."""
    if not description:
        return []

    items = []

    # Pattern: "30 Unit 2,359,790.00" or "1 Lot 5,000,000.00"
    pat = re.compile(
        r'(\d+)\s+(Unit|Lot|Set|Pack|Piece|pc|unit|lot|set)\s+([\d,]+(?:\.\d+)?)',
        re.IGNORECASE,
    )
    for qty, uom, amount in pat.findall(description):
        items.append({
            "quantity": int(qty),
            "uom": uom,
            "amount": float(amount.replace(",", "")),
        })

    return items


def _parse_php_amount(text: str) -> float | None:
    """Parse a PHP amount string like 'PHP60,000,000.00'."""
    if not text:
        return None
    match = re.search(r'(?:PHP|PhP|₱)\s*([\d,]+(?:\.\d+)?)', text, re.IGNORECASE)
    if match:
        return float(match.group(1).replace(',', ''))
    return None


def search_awards(agency: str | None = None) -> list[dict[str, Any]]:
    """Search recent contract awards.

    Note: PhilGEPS awards page is a JS-heavy ExtJS app that doesn't render
    with plain HTTP requests. This function is not yet implemented.
    Use web search or manual lookup for award data.
    """
    raise NotImplementedError(
        "PhilGEPS awards page requires JavaScript rendering. "
        "Use 'zxbyd detail show <ref_id>' on closed notices instead."
    )


def list_agencies() -> list[dict[str, str]]:
    """List all procuring entities on PhilGEPS."""
    raise NotImplementedError("Agency listing not yet implemented.")
