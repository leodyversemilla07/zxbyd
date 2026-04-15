"""PhilGEPS scraper and data source."""

from __future__ import annotations

from typing import Any

PHILGEPS_BASE = "https://notices.philgeps.gov.ph"


def search(query: str, max_pages: int = 1) -> list[dict[str, Any]]:
    """Search PhilGEPS procurement notices.

    Args:
        query: Search keywords.
        max_pages: Number of pages to scrape (20 results/page).

    Returns:
        List of notice dicts.
    """
    # TODO: implement Playwright scraper
    # Site is ASP.NET WebForms:
    # 1. Navigate to search page
    # 2. Click "Search" link to activate postback
    # 3. Type query into #txtKeyword
    # 4. Click #btnSearch
    # 5. Parse results table
    raise NotImplementedError("Scraper not yet implemented.")


def get_notice_detail(ref_id: str) -> dict[str, Any]:
    """Fetch full details for a procurement notice.

    Args:
        ref_id: PhilGEPS reference number.

    Returns:
        Notice detail dict.
    """
    raise NotImplementedError("Detail scraper not yet implemented.")


def search_awards(agency: str | None = None) -> list[dict[str, Any]]:
    """Search recent contract awards.

    Args:
        agency: Optional agency name filter.

    Returns:
        List of award dicts.
    """
    raise NotImplementedError("Awards scraper not yet implemented.")


def list_agencies() -> list[dict[str, str]]:
    """List all procuring entities on PhilGEPS.

    Returns:
        List of agency dicts with name and code.
    """
    raise NotImplementedError("Agency listing not yet implemented.")


def close() -> None:
    """Close browser/session resources."""
    pass
