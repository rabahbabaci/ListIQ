"""
ListIQ — Poshmark Sold Listings Scraper
========================================
Scrapes completed/sold listings from Poshmark using category pages
and the internal listing API.

Strategy:
  1. Fetch category pages (HTML) to collect listing IDs
  2. Fetch each listing via /vm-rest/posts/{id} for full structured data
  3. Paginate category pages using ?max_id=N

Usage:
    python scrapers/poshmark_scraper.py
    python scrapers/poshmark_scraper.py --categories "denim jacket,sneakers" --limit 100
"""

import re
import time
import argparse
from datetime import datetime
from pathlib import Path

import requests
import pandas as pd
from tqdm import tqdm

BASE_URL = "https://poshmark.com"
API_URL = f"{BASE_URL}/vm-rest/posts"

# Map our category names to Poshmark category page paths
CATEGORY_PATHS = {
    "denim jacket": "/category/Women-Jackets_&_Coats-Jean_Jackets",
    "midi dress": "/category/Women-Dresses-Midi_Dresses",
    "sneakers": "/category/Women-Shoes-Sneakers",
    "handbag": "/category/Women-Bags",
    "blazer": "/category/Women-Jackets_&_Coats-Blazers",
    "vintage t-shirt": "/category/Women-Tops-Tees_Short_Sleeve",
    "leather jacket": "/category/Women-Jackets_&_Coats-Leather_Jackets",
    "crossbody bag": "/category/Women-Bags-Crossbody_Bags",
}

DEFAULT_CATEGORIES = list(CATEGORY_PATHS.keys())

ITEMS_PER_PAGE = 48

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def get_listing_ids_from_page(category_path, max_id=None):
    """Fetch a category page and extract listing IDs from structured data."""
    url = f"{BASE_URL}{category_path}"
    params = {"availability": "sold_out"}
    if max_id is not None:
        params["max_id"] = max_id

    response = requests.get(url, headers=HEADERS, params=params, timeout=15)
    response.raise_for_status()

    # Extract listing IDs from Schema.org JSON-LD URLs embedded in HTML
    listing_ids = re.findall(
        r'poshmark\.com/listing/[^"]+?-([a-f0-9]{24})', response.text
    )
    # Deduplicate while preserving order
    seen = set()
    unique_ids = []
    for lid in listing_ids:
        if lid not in seen:
            seen.add(lid)
            unique_ids.append(lid)

    return unique_ids


def fetch_listing(listing_id):
    """Fetch full listing data from Poshmark's internal API."""
    url = f"{API_URL}/{listing_id}"
    headers = {**HEADERS, "Accept": "application/json"}

    response = requests.get(url, headers=headers, timeout=15)
    if response.status_code != 200:
        return None

    return response.json()


def parse_listing(data, category_name):
    """Parse a listing API response into our normalized schema."""
    try:
        title = data.get("title", "")
        brand = data.get("brand", "Unknown")
        price = data.get("price", 0)

        # Original list price: prefer first_user_price_amount (true original),
        # fall back to original_price
        orig_price_obj = data.get("first_user_price_amount", {})
        original_price = float(orig_price_obj.get("val", 0)) if orig_price_obj else 0
        if original_price == 0:
            original_price = data.get("original_price", 0)

        # Sold date from inventory status change
        inventory = data.get("inventory", {})
        sold_at_str = inventory.get("status_changed_at", "")
        sold_date = None
        if sold_at_str:
            try:
                sold_date = datetime.fromisoformat(sold_at_str).strftime("%Y-%m-%d")
            except (ValueError, AttributeError):
                pass

        # Listing date
        created_at_str = data.get("created_at", "")
        listing_day_of_week = None
        listing_time = None
        days_to_sale = None
        if created_at_str:
            try:
                created_dt = datetime.fromisoformat(created_at_str)
                listing_day_of_week = created_dt.strftime("%A")
                listing_time = created_dt.strftime("%H:%M")

                if sold_at_str:
                    sold_dt = datetime.fromisoformat(sold_at_str)
                    days_to_sale = (sold_dt - created_dt).days
            except (ValueError, AttributeError):
                pass

        return {
            "platform": "Poshmark",
            "item_category": category_name,
            "brand": brand,
            "condition": "Unknown",  # Poshmark has no structured condition field
            "final_sale_price": float(price),
            "original_list_price": float(original_price),
            "days_to_sale": days_to_sale,
            "listing_day_of_week": listing_day_of_week,
            "listing_time": listing_time,
            "sold_date": sold_date,
            "title": title,
            "item_id": data.get("id", ""),
            "image_url": data.get("picture_url", ""),
        }

    except Exception as e:
        print(f"  WARNING: Failed to parse listing: {e}")
        return None


def scrape_category(category_name, limit=100):
    """Scrape sold listings for a single category."""
    category_path = CATEGORY_PATHS.get(category_name)
    if not category_path:
        print(f"  WARNING: No category path mapped for '{category_name}'. Skipping.")
        return []

    all_items = []
    max_id = None
    pages_fetched = 0

    with tqdm(total=limit, desc=f"  {category_name}", unit="items") as pbar:
        while len(all_items) < limit:
            # Step 1: Get listing IDs from category page
            try:
                listing_ids = get_listing_ids_from_page(category_path, max_id)
            except Exception as e:
                print(f"\n  ERROR fetching category page: {e}")
                break

            if not listing_ids:
                break

            pages_fetched += 1
            time.sleep(1)

            # Step 2: Fetch each listing's full data
            for lid in listing_ids:
                if len(all_items) >= limit:
                    break

                try:
                    data = fetch_listing(lid)
                    if data:
                        parsed = parse_listing(data, category_name)
                        if parsed:
                            all_items.append(parsed)
                            pbar.update(1)
                except Exception as e:
                    continue

                # Rate limiting: ~1 request per second
                time.sleep(1)

            # Paginate: next page offset
            max_id = pages_fetched * ITEMS_PER_PAGE

    return all_items


def main():
    parser = argparse.ArgumentParser(
        description="Scrape Poshmark sold listings for ListIQ"
    )
    parser.add_argument(
        "--categories",
        type=str,
        default=",".join(DEFAULT_CATEGORIES),
        help="Comma-separated list of categories to scrape",
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
        default="data/raw/poshmark_sold_listings.csv",
        help="Output CSV path",
    )
    args = parser.parse_args()

    categories = [c.strip() for c in args.categories.split(",")]

    print("=" * 60)
    print("ListIQ — Poshmark Sold Listings Scraper")
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
