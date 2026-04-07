"""
ListIQ — Depop Listings Scraper
========================================
Scrapes listings from Depop using internal search API.

Strategy:
  1. Call Depop search API with query
  2. Parse product JSON
  3. Paginate using cursor

NOTE:
- Depop does NOT expose sold listings or timestamps
- Missing fields are set to None and should be documented

Usage:
    python scrapers/depop_scraper.py
    python scrapers/depop_scraper.py --categories "denim jacket,sneakers" --limit 100
"""
from playwright.sync_api import sync_playwright
import pandas as pd
import time
import argparse
from pathlib import Path
import re


def extract_price(text):
    """Extract price like $45 or $45.00 from text."""
    match = re.search(r"\$\d+(\.\d+)?", text)
    return float(match.group().replace("$", "")) if match else None


def scrape_category(category, limit=20):
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        url = f"https://www.depop.com/search/?q={category.replace(' ', '%20')}"
        page.goto(url)

        # ✅ FIX: wait for full page load instead of broken selector
        page.wait_for_load_state("networkidle")
        time.sleep(3)

        # Scroll to load listings
        for _ in range(5):
            page.mouse.wheel(0, 3000)
            time.sleep(1)

        # ✅ FIX: better selector
        items = page.query_selector_all('[data-testid="product-card"]')

        print(f"  Found {len(items)} items on page")

        for item in items[:limit]:
            try:
                text = item.inner_text()

                # Title = first line
                lines = text.split("\n")
                title = lines[0] if lines else None

                # Price
                price = extract_price(text)

                # Image
                img = item.query_selector("img")
                image_url = img.get_attribute("src") if img else None

                results.append({
                    "platform": "Depop",
                    "item_category": category,
                    "brand": None,
                    "condition": None,
                    "final_sale_price": price,
                    "original_list_price": None,
                    "days_to_sale": None,
                    "listing_day_of_week": None,
                    "listing_time": None,
                    "sold_date": None,
                    "title": title,
                    "item_id": None,
                    "image_url": image_url,
                })

            except Exception as e:
                print("  Skipping item due to error:", e)
                continue

        browser.close()

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Scrape Depop listings using Playwright"
    )
    parser.add_argument(
        "--categories",
        type=str,
        default="denim jacket",
        help="Comma-separated categories",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
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
    print("ListIQ — Depop Scraper (Playwright)")
    print("=" * 60)
    print(f"Categories: {categories}")
    print(f"Limit per category: {args.limit}")
    print(f"Output: {args.output}\n")

    all_data = []

    for category in categories:
        print(f"Scraping: {category}")
        items = scrape_category(category, args.limit)
        all_data.extend(items)
        print(f"  Got {len(items)} items\n")
        time.sleep(2)

    df = pd.DataFrame(all_data)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    print("=" * 60)
    print(f"Done! Saved {len(df)} listings to {args.output}")
    print("=" * 60)


if __name__ == "__main__":
    main()
"""
import time
import argparse
from datetime import datetime
from pathlib import Path

import requests
import pandas as pd
from tqdm import tqdm

BASE_URL = "https://webapi.depop.com/api/v3/search/products/"

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

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9",
    "origin": "https://www.depop.com",
    "referer": "https://www.depop.com/",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "x-requested-with": "XMLHttpRequest",
}

def fetch_products(query, cursor=None):
    //Fetch a page of products from Depop API.
    params = {
        "what": query,
        "items_per_page": 24,
        "country": "us",
        "currency": "USD",
        "force_fee_calculation": "true",
        "from": "in_country_search",
        "include_like_count": "false",
    }

    if cursor:
        params["cursor"] = cursor

    response = requests.get(BASE_URL, headers=HEADERS, params=params, timeout=15)

    if response.status_code != 200:
        print(f"  ERROR: Status {response.status_code}")
        return None

    return response.json()


def map_condition(raw):
    //Normalize Depop condition to required schema.
    if not raw:
        return None

    raw = str(raw).lower()

    if "new" in raw:
        return "New"
    elif "like" in raw:
        return "Like New"
    elif "good" in raw:
        return "Good"
    else:
        return "Fair"


def parse_product(product, category_name):
    //Convert Depop product JSON into schema.
    try:
        price_obj = product.get("price", {})
        pictures = product.get("pictures_data", []) or product.get("pictures", [])

        image_url = None
        if pictures:
            image_url = pictures[0].get("url") or pictures[0].get("secure_url")

        return {
            "platform": "Depop",
            "item_category": category_name,
            "brand": product.get("brand"),
            "condition": map_condition(product.get("condition")),
            "final_sale_price": price_obj.get("amount"),
            "original_list_price": None,  # Not available
            "days_to_sale": None,         # Not available
            "listing_day_of_week": None,  # Not available
            "listing_time": None,         # Not available
            "sold_date": None,            # Not available
            "title": product.get("title") or product.get("description"),
            "item_id": product.get("id"),
            "image_url": image_url,
        }

    except Exception as e:
        print(f"  WARNING: Failed to parse product: {e}")
        return None


def scrape_category(category, limit=100):
    //Scrape a single category.
    all_items = []
    cursor = None

    with tqdm(total=limit, desc=f"  {category}", unit="items") as pbar:
        while len(all_items) < limit:
            data = fetch_products(category, cursor)

            if not data:
                break

            products = data.get("products", [])
            if not products:
                break

            for product in products:
                if len(all_items) >= limit:
                    break

                parsed = parse_product(product, category)
                if parsed:
                    all_items.append(parsed)
                    pbar.update(1)

            # Pagination
            meta = data.get("meta", {})
            if not meta.get("has_more"):
                break

            cursor = meta.get("cursor")

            time.sleep(1)  # rate limiting

    return all_items


def main():
    parser = argparse.ArgumentParser(
        description="Scrape Depop listings for ListIQ"
    )
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
    print("ListIQ — Depop Listings Scraper")
    print("=" * 60)
    print(f"Categories: {categories}")
    print(f"Limit per category: {args.limit}")
    print(f"Output: {args.output}")
    print()

    all_data = []

    for category in categories:
        print(f"Scraping: {category}")
        items = scrape_category(category, args.limit)
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
"""