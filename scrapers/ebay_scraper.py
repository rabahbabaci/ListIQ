"""
ListIQ — eBay Sold Listings Scraper
====================================
Scrapes completed/sold listings from eBay's Browse API.

Setup:
1. Create an eBay developer account at https://developer.ebay.com/
2. Create an application to get your App ID (Client ID) and Client Secret
3. Create a .env file in the repo root with:
   EBAY_CLIENT_ID=your_client_id
   EBAY_CLIENT_SECRET=your_client_secret

Usage:
    python scrapers/ebay_scraper.py
    python scrapers/ebay_scraper.py --categories "denim jacket,sneakers" --limit 500
"""

import os
import sys
import json
import time
import argparse
import base64
from datetime import datetime, timedelta
from pathlib import Path

import requests
import pandas as pd
from tqdm import tqdm
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

EBAY_CLIENT_ID = os.getenv("EBAY_CLIENT_ID")
EBAY_CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")

# eBay Browse API endpoints
TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"

# Default categories to scrape
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

# Maximum items per category
DEFAULT_LIMIT_PER_CATEGORY = 500


def get_access_token():
    """Get OAuth2 access token from eBay."""
    if not EBAY_CLIENT_ID or not EBAY_CLIENT_SECRET:
        print("ERROR: Missing eBay API credentials.")
        print("Create a .env file in the repo root with:")
        print("  EBAY_CLIENT_ID=your_client_id")
        print("  EBAY_CLIENT_SECRET=your_client_secret")
        print("\nGet credentials at: https://developer.ebay.com/")
        sys.exit(1)

    credentials = base64.b64encode(
        f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}".encode()
    ).decode()

    response = requests.post(
        TOKEN_URL,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {credentials}",
        },
        data={
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope",
        },
    )

    if response.status_code != 200:
        print(f"ERROR: Failed to get access token: {response.status_code}")
        print(response.text)
        sys.exit(1)

    return response.json()["access_token"]


def search_sold_items(token, query, limit=200, offset=0):
    """Search for sold/completed items on eBay."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
    }

    params = {
        "q": query,
        "filter": "buyingOptions:{FIXED_PRICE},conditions:{NEW|LIKE_NEW|GOOD|FAIR}",
        "sort": "newlyListed",
        "limit": min(limit, 200),  # eBay max is 200 per request
        "offset": offset,
        # Focus on clothing/fashion
        "category_ids": "11450",  # Clothing, Shoes & Accessories
    }

    response = requests.get(SEARCH_URL, headers=headers, params=params)

    if response.status_code == 429:
        print("  Rate limited — waiting 5 seconds...")
        time.sleep(5)
        return search_sold_items(token, query, limit, offset)

    if response.status_code != 200:
        print(f"  WARNING: API returned {response.status_code} for query '{query}'")
        return {"itemSummaries": [], "total": 0}

    return response.json()


def parse_item(item, category_query):
    """Parse a single item from the API response into our schema."""
    try:
        # Extract price
        price = float(item.get("price", {}).get("value", 0))
        currency = item.get("price", {}).get("currency", "USD")

        # Only keep USD items
        if currency != "USD":
            return None

        # Extract condition — prefer conditionId (structured), fall back to condition string
        condition_id = item.get("conditionId", "")
        condition_str = item.get("condition", "")

        # Map eBay condition IDs to our schema
        condition_id_map = {
            "1000": "New",
            "1500": "New",
            "2000": "Like New",
            "2500": "Like New",
            "2750": "Like New",
            "2990": "Like New",
            "3000": "Good",
            "4000": "Good",
            "5000": "Fair",
            "6000": "Fair",
        }

        # Map eBay condition strings to our schema
        condition_str_map = {
            "new with tags": "New",
            "new without tags": "Like New",
            "new with defects": "Like New",
            "pre-owned - like new": "Like New",
            "pre-owned - excellent": "Like New",
            "pre-owned - good": "Good",
            "pre-owned - fair": "Fair",
            "pre-owned": "Good",
        }

        condition = condition_id_map.get(str(condition_id), "")
        if not condition and isinstance(condition_str, str):
            condition = condition_str_map.get(condition_str.lower().strip(), "Unknown")
        condition = condition or "Unknown"

        # Extract listing date
        item_creation_date = item.get("itemCreationDate", "")
        listing_date = None
        listing_day_of_week = None
        listing_time = None

        if item_creation_date:
            try:
                dt = datetime.fromisoformat(item_creation_date.replace("Z", "+00:00"))
                listing_date = dt.strftime("%Y-%m-%d")
                listing_day_of_week = dt.strftime("%A")
                listing_time = dt.strftime("%H:%M")
            except (ValueError, AttributeError):
                pass

        # Extract brand from title (basic extraction)
        title = item.get("title", "")
        brand = extract_brand(title)

        return {
            "platform": "eBay",
            "item_category": category_query,
            "brand": brand,
            "condition": condition,
            "final_sale_price": price,
            "original_list_price": price,  # Browse API doesn't always separate these
            "days_to_sale": None,  # Not available from Browse API search
            "listing_day_of_week": listing_day_of_week,
            "listing_time": listing_time,
            "sold_date": listing_date,  # Using listing date as proxy
            "title": title,
            "item_id": item.get("itemId", ""),
            "image_url": item.get("image", {}).get("imageUrl", ""),
        }

    except Exception as e:
        print(f"  WARNING: Failed to parse item: {e}")
        return None


def extract_brand(title):
    """Extract brand name from listing title (basic heuristic)."""
    known_brands = [
        "Nike", "Adidas", "Zara", "H&M", "Gucci", "Prada", "Louis Vuitton",
        "Chanel", "Levi's", "Levis", "Ralph Lauren", "Calvin Klein",
        "Tommy Hilfiger", "Gap", "Uniqlo", "Mango", "ASOS", "Topshop",
        "Free People", "Anthropologie", "J.Crew", "Banana Republic",
        "Coach", "Michael Kors", "Kate Spade", "Tory Burch",
        "Burberry", "Versace", "Fendi", "Balenciaga", "Saint Laurent",
        "Reformation", "Everlane", "Patagonia", "North Face",
        "Lululemon", "Alo", "New Balance", "Converse", "Vans",
        "Doc Martens", "Dr. Martens", "Birkenstock", "Steve Madden",
    ]

    title_lower = title.lower()
    for brand in known_brands:
        if brand.lower() in title_lower:
            return brand
    return "Unknown"


def scrape_category(token, category, limit):
    """Scrape sold listings for a single category."""
    all_items = []
    offset = 0

    with tqdm(total=limit, desc=f"  {category}", unit="items") as pbar:
        while len(all_items) < limit:
            batch_size = min(200, limit - len(all_items))
            data = search_sold_items(token, category, batch_size, offset)

            items = data.get("itemSummaries", [])
            if not items:
                break

            for item in items:
                parsed = parse_item(item, category)
                if parsed:
                    all_items.append(parsed)
                    pbar.update(1)

                if len(all_items) >= limit:
                    break

            offset += len(items)
            total = data.get("total", 0)
            if offset >= total:
                break

            # Be nice to the API
            time.sleep(0.5)

    return all_items


def main():
    parser = argparse.ArgumentParser(description="Scrape eBay sold listings for ListIQ")
    parser.add_argument(
        "--categories",
        type=str,
        default=",".join(DEFAULT_CATEGORIES),
        help="Comma-separated list of categories to scrape",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT_PER_CATEGORY,
        help="Max items per category",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/raw/ebay_sold_listings.csv",
        help="Output CSV path",
    )
    args = parser.parse_args()

    categories = [c.strip() for c in args.categories.split(",")]

    print("=" * 60)
    print("ListIQ — eBay Sold Listings Scraper")
    print("=" * 60)
    print(f"Categories: {categories}")
    print(f"Limit per category: {args.limit}")
    print(f"Output: {args.output}")
    print()

    # Authenticate
    print("Authenticating with eBay API...")
    token = get_access_token()
    print("Authenticated successfully.\n")

    # Scrape each category
    all_data = []
    for category in categories:
        print(f"Scraping: {category}")
        items = scrape_category(token, category, args.limit)
        all_data.extend(items)
        print(f"  Got {len(items)} items\n")

    # Convert to DataFrame
    df = pd.DataFrame(all_data)

    # Save
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    print("=" * 60)
    print(f"Done! Saved {len(df)} total listings to {args.output}")
    print(f"Categories scraped: {len(categories)}")
    print(f"Breakdown:")
    if not df.empty:
        for cat, count in df["item_category"].value_counts().items():
            print(f"  {cat}: {count}")
    print("=" * 60)


if __name__ == "__main__":
    main()
