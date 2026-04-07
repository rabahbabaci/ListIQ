"""
ListIQ — Depop Listings Scraper (v2)
========================================
Scrapes listings from Depop using two endpoints:

  1. Product list:  https://webapi.depop.com/api/v3/search/products/
     Paginated via the `cursor` returned in `meta.cursor`. This is the
     same JSON Depop's own SPA uses for "load more" / infinite scroll.
     Direct hits 403 (Cloudflare); we get through by warming up a
     curl_cffi Session against www.depop.com first and then sending
     Origin/Referer headers.

  2. Product title: https://www.depop.com/products/{slug}/
     The API does not return a real listing title (only a URL slug),
     so for each product we make ONE additional request to its detail
     page and read `<meta property="og:title">`.

Why curl_cffi instead of requests:
  Depop is fronted by Cloudflare and 403s Python's default urllib3 TLS
  fingerprint. curl_cffi impersonates Chrome's TLS handshake.

IMPORTANT — Depop data limitations
----------------------------------
1. Depop does NOT expose `condition` on any public web endpoint. The
   product detail page renders condition via a client-side React lazy
   component that fetches from an authenticated API after hydration.
   Without an authenticated session (or running real JS via Playwright),
   condition is unreachable. We set it to None and document this in
   CLAUDE.md alongside the other null-field caveats.

2. Depop does NOT expose sold history publicly. The `final_sale_price`
   column for Depop rows is the currently-LISTED price, not a sold price.
   Treat Depop rows as "listed price / market positioning" rather than
   "what items actually sold for." This is the same reason the original
   eBay API path was abandoned in favor of the completed-listings page
   scrape.

Usage:
    python scrapers/depop_scraper_v2.py
    python scrapers/depop_scraper_v2.py --categories "denim jacket,sneakers" --limit 100
"""

import re
import html
import time
import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd
from tqdm import tqdm
from curl_cffi import requests

SEARCH_API_URL = "https://webapi.depop.com/api/v3/search/products/"
WARMUP_URL = "https://www.depop.com/"
PRODUCT_URL = "https://www.depop.com/products/{slug}/"

DEFAULT_CATEGORIES = [
    "denim jacket",
    "midi dress",
    "sneakers",
    "handbag",
    "blazer",
    "vintage t-shirt",
    "leather jacket",
    "crossbody bag",
]

ITEMS_PER_PAGE = 24

API_HEADERS = {
    "Origin": "https://www.depop.com",
    "Referer": "https://www.depop.com/",
    "Accept": "application/json, text/plain, */*",
}


def make_session():
    """Create a curl_cffi session impersonating Chrome and warm it up by
    hitting www.depop.com first. Without the warmup, the webapi.depop.com
    subdomain returns 403."""
    s = requests.Session(impersonate="chrome124")
    try:
        s.get(WARMUP_URL, timeout=20)
    except Exception as e:
        print(f"  WARNING: warmup hit failed: {e}")
    return s


def fetch_search_page(session, query, cursor=None):
    """Fetch one page of search results from the Depop JSON API.
    Returns the parsed JSON dict, or None on error."""
    params = {
        "what": query,
        "items_per_page": ITEMS_PER_PAGE,
        "country": "us",
        "currency": "USD",
    }
    if cursor:
        params["cursor"] = cursor

    try:
        r = session.get(SEARCH_API_URL, params=params, headers=API_HEADERS, timeout=20)
    except Exception as e:
        print(f"  ERROR: search request failed: {e}")
        return None

    if r.status_code != 200:
        print(f"  ERROR: search status {r.status_code} for '{query}'")
        return None

    try:
        return r.json()
    except ValueError:
        print(f"  ERROR: search response not JSON for '{query}'")
        return None


def fetch_product_title(session, slug):
    """Fetch a product detail page and read its og:title meta tag."""
    try:
        r = session.get(PRODUCT_URL.format(slug=slug), timeout=20)
    except Exception:
        return None
    if r.status_code != 200:
        return None
    m = re.search(
        r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', r.text
    )
    if not m:
        return None
    title = m.group(1)
    # Decode HTML entities (Depop ships og:title as e.g. "Levi&#x27;s ...")
    title = html.unescape(title)
    # Collapse any embedded newlines/whitespace runs into single spaces
    title = re.sub(r"\s+", " ", title).strip()
    # Strip the trailing " | Depop" suffix Depop appends
    if title.endswith(" | Depop"):
        title = title[: -len(" | Depop")].strip()
    return title or None


def parse_pricing(pricing):
    """Return (final_sale_price, original_list_price) from a Depop pricing
    block. Depop always has `original_price`; `discounted_price` only
    appears when the seller marked the item down. We use `final_price_key`
    to decide which is "current"."""
    def amount_of(block):
        try:
            return float(block["price_breakdown"]["price"]["amount"])
        except (KeyError, TypeError, ValueError):
            return None

    original_block = pricing.get("original_price") or {}
    discounted_block = pricing.get("discounted_price") or {}

    original_amount = amount_of(original_block)
    discounted_amount = amount_of(discounted_block)

    final_key = pricing.get("final_price_key", "original_price")

    if final_key == "discounted_price" and discounted_amount is not None:
        # Item is reduced — current price is discounted, original is the markdown source
        return discounted_amount, original_amount
    # Item is not reduced — current price is original, no separate "original list"
    return original_amount, None


def parse_date_created(date_str):
    """Parse Depop's ISO timestamp into (day_of_week, listing_time).
    Depop dates look like '2026-04-07T01:27:34.574871Z'."""
    if not date_str:
        return None, None
    try:
        clean = date_str.rstrip("Z")
        dt = datetime.fromisoformat(clean)
        return dt.strftime("%A"), dt.strftime("%H:%M")
    except (ValueError, AttributeError):
        return None, None


def first_picture_url(pictures):
    """Pick the largest image URL from the first picture in the list."""
    if not pictures:
        return None
    first = pictures[0]
    if not isinstance(first, dict):
        return None
    for size in ("1280", "960", "640", "480", "320", "210", "150"):
        url = first.get(size)
        if url:
            return url
    return None


def map_product(session, product, category_name):
    """Convert a Depop product dict (+ detail-page title) into our schema."""
    pricing = product.get("pricing", {}) or {}
    final_price, original_list_price = parse_pricing(pricing)

    day_of_week, listing_time = parse_date_created(product.get("date_created"))

    title = None
    slug = product.get("slug")
    if slug:
        title = fetch_product_title(session, slug)
        # Be a polite client between detail-page hits
        time.sleep(0.5)

    return {
        "platform": "Depop",
        "item_category": category_name,
        "brand": product.get("brand_name"),
        "condition": None,  # See module docstring — not exposed publicly
        "final_sale_price": final_price,
        "original_list_price": original_list_price,
        "days_to_sale": None,  # Active listings, not sold
        "listing_day_of_week": day_of_week,
        "listing_time": listing_time,
        "sold_date": None,  # Active listings, not sold
        "title": title,
        "item_id": product.get("id"),
        "image_url": first_picture_url(product.get("pictures")),
    }


def scrape_category(session, category, limit=100):
    """Scrape a single category up to `limit` items via cursor pagination."""
    all_items = []
    cursor = None
    seen_ids = set()

    with tqdm(total=limit, desc=f"  {category}", unit="items") as pbar:
        while len(all_items) < limit:
            data = fetch_search_page(session, category, cursor=cursor)
            if not data:
                break

            products = data.get("products", []) or []
            if not products:
                break

            new_on_page = 0
            for product in products:
                if len(all_items) >= limit:
                    break
                pid = product.get("id")
                if pid is None or pid in seen_ids:
                    continue
                seen_ids.add(pid)
                row = map_product(session, product, category)
                if row:
                    all_items.append(row)
                    pbar.update(1)
                    new_on_page += 1

            meta = data.get("meta", {}) or {}
            if not meta.get("has_more"):
                break
            next_cursor = meta.get("cursor")
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor

            if new_on_page == 0:
                # Cursor advanced but no new IDs — bail to avoid an infinite loop
                break

            time.sleep(1)  # be respectful between search-API hits

    return all_items


def main():
    parser = argparse.ArgumentParser(description="Scrape Depop listings for ListIQ")
    parser.add_argument(
        "--categories",
        type=str,
        default=",".join(DEFAULT_CATEGORIES),
        help="Comma-separated list of categories",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Max items per category",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/raw/depop_sold_listings.csv",
        help="Output CSV path",
    )

    args = parser.parse_args()
    categories = [c.strip() for c in args.categories.split(",")]

    print("=" * 60)
    print("ListIQ — Depop Listings Scraper (v2)")
    print("=" * 60)
    print(f"Categories: {categories}")
    print(f"Limit per category: {args.limit}")
    print(f"Output: {args.output}\n")

    session = make_session()

    all_data = []
    for category in categories:
        print(f"Scraping: {category}")
        items = scrape_category(session, category, args.limit)
        all_data.extend(items)
        print(f"  Got {len(items)} items\n")
        time.sleep(2)

    df = pd.DataFrame(all_data)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    print("=" * 60)
    print(f"Done! Saved {len(df)} total listings to {args.output}")
    if not df.empty:
        print(f"Categories scraped: {df['item_category'].nunique()}")
        print("Breakdown:")
        for cat, count in df["item_category"].value_counts().items():
            print(f"  {cat}: {count}")
    print("=" * 60)


if __name__ == "__main__":
    main()
