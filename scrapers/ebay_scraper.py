"""
ListIQ — eBay Sold Listings Scraper
====================================
Scrapes completed/sold listings from eBay's public completed-listings page
using Playwright (headless Chromium).

eBay's Browse API only exposes active listings, and the Marketplace Insights
API (which has sold data) is gated to approved partners. This scraper pulls
from the public sold-results page instead:

  https://www.ebay.com/sch/i.html?_nkw=...&LH_Complete=1&LH_Sold=1

Setup:
    pip install playwright
    playwright install chromium

Usage:
    python scrapers/ebay_scraper.py
    python scrapers/ebay_scraper.py --categories "denim jacket,sneakers" --limit 500
    python scrapers/ebay_scraper.py --output data/raw/ebay_sold_listings.csv
"""

import re
import time
import random
import argparse
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd
from tqdm import tqdm
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError
from playwright_stealth import Stealth


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

DEFAULT_LIMIT_PER_CATEGORY = 500
ITEMS_PER_PAGE = 240  # eBay max

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


# Map common eBay condition labels to our 4-bucket schema
CONDITION_MAP = {
    "new with tags": "New",
    "new with box": "New",
    "new without tags": "Like New",
    "new without box": "Like New",
    "new with defects": "Like New",
    "brand new": "New",
    "new (other)": "Like New",
    "new other": "Like New",
    "new other (see details)": "Like New",
    "new": "New",
    "open box": "Like New",
    "like new": "Like New",
    "pre-owned": "Good",
    "preowned": "Good",
    "pre owned": "Good",
    "used": "Good",
    "very good": "Good",
    "good": "Good",
    "acceptable": "Fair",
    "fair": "Fair",
    "for parts or not working": "Fair",
}


# Hardcoded brand list — checked against listing titles in priority order.
# Multi-word brands MUST come before single-word ones that could match as a
# substring (e.g. "Saint Laurent" before "Laurent", "True Religion" before
# "Religion"). The list is title-cased; matching is case-insensitive.
KNOWN_BRANDS = [
    # --- Denim / Americana ---
    "Levi's", "Levis", "Wrangler", "True Religion", "Diesel", "Guess",
    "Lucky Brand", "Calvin Klein", "Tommy Hilfiger", "Tommy Jeans",
    "7 For All Mankind", "Citizens of Humanity", "AG Jeans", "AG Adriano Goldschmied",
    "Paige", "Hudson", "Frame", "Mother", "Joe's Jeans", "Rock Revival",
    "Miss Me", "Buckle", "BKE", "Silver Jeans", "Lee", "Pepe Jeans",
    "G-Star", "G Star Raw", "Nudie Jeans",
    # --- Athletic / Activewear ---
    "Nike", "Air Jordan", "Jordan", "Adidas", "Yeezy", "Puma", "Reebok",
    "Under Armour", "New Balance", "Asics", "Brooks", "Saucony",
    "Hoka", "On Running", "Salomon", "Mizuno",
    "Lululemon", "Alo Yoga", "Alo", "Athleta", "Fabletics", "Gymshark",
    "Sweaty Betty", "Outdoor Voices", "Vuori", "Bandier",
    # --- Outdoor ---
    "Patagonia", "The North Face", "North Face", "Columbia", "Arc'teryx",
    "Arcteryx", "Mountain Hardwear", "REI", "Marmot", "Cotopaxi",
    "Eddie Bauer", "L.L. Bean", "LL Bean", "Filson", "Pendleton",
    # --- Luxury ---
    "Louis Vuitton", "Gucci", "Prada", "Chanel", "Hermès", "Hermes",
    "Dior", "Christian Dior", "Saint Laurent", "Yves Saint Laurent", "YSL",
    "Balenciaga", "Bottega Veneta", "Givenchy", "Valentino", "Versace",
    "Fendi", "Burberry", "Celine", "Loewe", "Miu Miu", "Moncler",
    "Off-White", "Off White", "Maison Margiela", "Margiela", "Acne Studios",
    "Brunello Cucinelli", "Loro Piana", "Tom Ford", "Stella McCartney",
    "Alexander McQueen", "Alexander Wang", "Marc Jacobs", "Jimmy Choo",
    "Manolo Blahnik", "Christian Louboutin", "Salvatore Ferragamo", "Ferragamo",
    # --- Accessible luxury / contemporary handbag brands ---
    "Coach", "Michael Kors", "Kate Spade", "Tory Burch", "Rebecca Minkoff",
    "Marc By Marc Jacobs", "Furla", "Longchamp", "Mulberry", "Tumi",
    # --- Contemporary / mall ---
    "Zara", "H&M", "Uniqlo", "Mango", "ASOS", "Topshop", "Forever 21",
    "Urban Outfitters", "Anthropologie", "Free People", "Madewell",
    "J.Crew", "J Crew", "Banana Republic", "Gap", "Old Navy", "Loft",
    "Ann Taylor", "Talbots", "Express", "Aritzia", "Wilfred", "Tna",
    "Reformation", "Everlane", "& Other Stories", "COS", "Massimo Dutti",
    "Abercrombie & Fitch", "Abercrombie", "Hollister", "American Eagle",
    "Aerie", "PacSun", "Brandy Melville", "Princess Polly", "Revolve",
    # --- Streetwear / vintage ---
    "Supreme", "Stussy", "Stüssy", "Carhartt", "Carhartt WIP", "Dickies",
    "Champion", "Fila", "Kappa", "Ellesse", "Bape", "A Bathing Ape",
    "Palace", "Stone Island", "Comme des Garçons", "Comme Des Garcons",
    "CDG", "Thrasher", "Obey", "Huf", "The Hundreds", "Diamond Supply",
    "Anti Social Social Club", "Kith", "Aimé Leon Dore", "Aime Leon Dore",
    "Fear of God", "Essentials", "Rhude", "Amiri", "Chrome Hearts",
    # --- Footwear ---
    "Converse", "Vans", "Doc Martens", "Dr. Martens", "Dr Martens",
    "Birkenstock", "Steve Madden", "Sam Edelman", "Stuart Weitzman",
    "Cole Haan", "Clarks", "Timberland", "UGG", "Crocs", "Toms",
    "Keds", "Sperry", "Allen Edmonds",
    # --- Jewelry / watches (sometimes in fashion listings) ---
    "Tiffany & Co", "Tiffany", "Pandora", "Rolex", "Cartier", "Omega",
    # --- Other commonly listed ---
    "Disney", "Harley Davidson", "Harley-Davidson", "Polo Ralph Lauren",
    "Ralph Lauren", "Lauren Ralph Lauren", "Lauren", "Brooks Brothers",
    "Vineyard Vines", "Lacoste", "Fred Perry", "Ben Sherman",
    "St. John", "St John", "Eileen Fisher", "Tory Sport", "Vera Bradley",
    "Tony Alamo", "Pendleton", "Woolrich",
]
# Sort by length descending so multi-word brands match before shorter substrings.
KNOWN_BRANDS = sorted(set(KNOWN_BRANDS), key=len, reverse=True)


def _brand_pattern(brand):
    """Build a case-insensitive regex that matches `brand` as a whole token.

    Uses non-letter lookarounds instead of \\b so it works with brands that
    contain non-word characters like '&', '.', or apostrophes (H&M, J.Crew, Levi's).
    """
    return re.compile(
        r"(?<![a-z])" + re.escape(brand) + r"(?![a-z])",
        re.IGNORECASE,
    )


# Pre-compile once at import time. Already length-sorted (longest first) so
# multi-word brands win over single-word substrings.
_BRAND_PATTERNS = [(brand, _brand_pattern(brand)) for brand in KNOWN_BRANDS]


def _normalize_quotes(text):
    """Replace curly/smart quotes with straight ASCII equivalents.

    eBay titles frequently use ’ (U+2019) instead of ', which broke brand
    matching for names like Levi's, Dr. Martens, etc.
    """
    return (
        text.replace("\u2019", "'")
            .replace("\u2018", "'")
            .replace("\u201C", '"')
            .replace("\u201D", '"')
    )


def extract_brand(title):
    """Extract brand name from listing title using a hardcoded known-brand list."""
    if not title:
        return "Unknown"
    normalized = _normalize_quotes(title)
    for brand, pattern in _BRAND_PATTERNS:
        if pattern.search(normalized):
            return brand
    return "Unknown"


def normalize_condition(raw):
    """Map a raw eBay condition label to our schema (New / Like New / Good / Fair)."""
    if not raw:
        return "Unknown"
    key = raw.lower().strip().rstrip(".")
    if key in CONDITION_MAP:
        return CONDITION_MAP[key]
    # Substring fallback for compound labels
    for needle, mapped in CONDITION_MAP.items():
        if needle in key:
            return mapped
    return "Unknown"


def parse_price(text):
    """Parse a price string like '$24.99' or '$10.00 to $25.00' into a float (low end)."""
    if not text:
        return None
    # Take the first $X.XX match
    m = re.search(r"\$([\d,]+(?:\.\d{1,2})?)", text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def parse_sold_date(text):
    """Parse 'Sold  Mar 15, 2026' or 'Sold Mar 15, 2026' into YYYY-MM-DD."""
    if not text:
        return None
    # Strip 'Sold' prefix and any whitespace
    cleaned = re.sub(r"^\s*sold\s*", "", text, flags=re.IGNORECASE).strip()
    # Try common eBay date formats
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def parse_item_id(url):
    """Extract eBay item ID from a listing URL like /itm/123456789012."""
    if not url:
        return ""
    m = re.search(r"/itm/(?:[^/]+/)?(\d{9,})", url)
    return m.group(1) if m else ""


def build_search_url(query, page, sort=None):
    """Build an eBay completed/sold listings search URL.

    `sort` is the value of eBay's `_sop` query param:
      None / not set → default (recency / newly sold first)
      15             → lowest price first (useful for paginating into older inventory)
      12             → highest price first
    """
    url = (
        "https://www.ebay.com/sch/i.html"
        f"?_nkw={quote_plus(query)}"
        f"&_sacat=0"
        f"&LH_Complete=1"
        f"&LH_Sold=1"
        f"&_ipg={ITEMS_PER_PAGE}"
        f"&_pgn={page}"
    )
    if sort is not None:
        url += f"&_sop={sort}"
    return url


def parse_results_page(page, category_query):
    """Extract sold-listing rows from the currently loaded results page.

    Returns a list of dicts matching the shared schema. Uses Playwright's
    JS-evaluation to walk every li.s-card on the page in one shot.

    Page structure (eBay 2025+ redesign):
      li.s-card[data-listingid]      — one card per listing
      .s-card__title                  — title (with trailing "Opens in a new window..." to strip)
      .s-card__subtitle               — "Pre-Owned · Size XL" (condition before the bullet)
      .s-card__price                  — current price
      a.s-card__link[href]            — listing URL
      img.s-card__image               — thumbnail
      Sold date is rendered as text like "Sold Apr 6, 2026" in the card body.
    """
    items = page.evaluate(
        """
        () => {
            const cards = Array.from(document.querySelectorAll('li.s-card'));
            return cards.map(card => {
                const get = (sel) => {
                    const el = card.querySelector(sel);
                    return el ? el.textContent.trim() : '';
                };
                const getAttr = (sel, attr) => {
                    const el = card.querySelector(sel);
                    return el ? (el.getAttribute(attr) || '') : '';
                };
                const img = card.querySelector('img.s-card__image');
                const imgUrl = img ? (img.getAttribute('src') || img.getAttribute('data-defer-load') || '') : '';
                return {
                    listing_id: card.getAttribute('data-listingid') || '',
                    title: get('.s-card__title'),
                    url: getAttr('a.s-card__link', 'href'),
                    price_text: get('.s-card__price'),
                    subtitle_text: get('.s-card__subtitle'),
                    full_text: card.innerText || '',
                    image_url: imgUrl,
                };
            });
        }
        """
    )

    parsed = []
    for raw in items:
        listing_id = (raw.get("listing_id") or "").strip()
        title = (raw.get("title") or "").strip()
        # Strip eBay's "Opens in a new window or tab" suffix
        title = re.sub(r"\s*Opens in a new window or tab\s*$", "", title, flags=re.IGNORECASE).strip()

        # Skip the "Shop on eBay" placeholder card
        if not title or title.lower() == "shop on ebay":
            continue
        if not listing_id or not listing_id.isdigit():
            continue

        sold_price = parse_price(raw.get("price_text"))
        if sold_price is None:
            continue

        # Condition: subtitle is "Pre-Owned · Size M" — keep the part before the bullet
        subtitle = (raw.get("subtitle_text") or "").strip()
        condition_raw = re.split(r"[·•|]", subtitle, maxsplit=1)[0].strip() if subtitle else ""
        condition = normalize_condition(condition_raw)

        # Sold date: extract from the card's full text, e.g. "Sold Apr 6, 2026"
        full_text = raw.get("full_text") or ""
        sold_date_match = re.search(
            r"Sold\s+([A-Z][a-z]{2,8}\s+\d{1,2},\s+\d{4})",
            full_text,
        )
        sold_date = parse_sold_date(sold_date_match.group(1)) if sold_date_match else None

        # Original list price: eBay sometimes shows a strikethrough "was $X" — not common
        # in the new layout's main price element, so leave null for now.
        original_price = None

        brand = extract_brand(title)

        parsed.append({
            "platform": "eBay",
            "item_category": category_query,
            "brand": brand,
            "condition": condition,
            "final_sale_price": sold_price,
            "original_list_price": original_price,
            "days_to_sale": None,
            "listing_day_of_week": None,
            "listing_time": None,
            "sold_date": sold_date,
            "title": title,
            "item_id": listing_id,
            "image_url": raw.get("image_url", ""),
        })

    return parsed


def _scrape_pass(page, category, target, sort, seen_ids, pbar):
    """Run one sort-pass for a category. Mutates `seen_ids` and `pbar`.

    Returns the list of new (unseen) rows collected from this pass, up to
    `target` items.
    """
    collected = []
    page_num = 1

    while len(collected) < target:
        url = build_search_url(category, page_num, sort=sort)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except PWTimeoutError:
            print(f"\n  WARNING: timeout loading page {page_num} for '{category}' (sort={sort})")
            break

        try:
            page.wait_for_selector("li.s-card", timeout=15000)
        except PWTimeoutError:
            if "splashui" in page.url.lower() or "captcha" in page.url.lower():
                print(f"\n  STOPPED: eBay anti-bot challenge on '{category}' page {page_num} (sort={sort}). Saving what we have.")
            break

        rows = parse_results_page(page, category)
        if not rows:
            break

        new_count = 0
        for r in rows:
            if r["item_id"] in seen_ids:
                continue
            seen_ids.add(r["item_id"])
            collected.append(r)
            new_count += 1
            pbar.update(1)
            if len(collected) >= target:
                break

        if new_count == 0:
            break

        page_num += 1
        time.sleep(random.uniform(2.0, 4.0))

    return collected


def scrape_category(browser_context, category, limit):
    """Scrape sold listings for a single category.

    Splits the budget across two sort orders to broaden date coverage:
      - half with default recency sort (newly sold first)
      - half with _sop=15 (lowest price first), which paginates through cheaper
        inventory and naturally surfaces older sold dates
    Results are deduplicated by item_id across both passes.
    """
    seen_ids = set()
    page = browser_context.new_page()

    half = max(1, limit // 2)
    second_half = limit - half

    with tqdm(total=limit, desc=f"  {category}", unit="items") as pbar:
        # Pass 1: recency (default sort)
        pass1 = _scrape_pass(page, category, half, None, seen_ids, pbar)
        # Pass 2: lowest price first — pulls in items missed by recency
        pass2 = _scrape_pass(page, category, second_half, 15, seen_ids, pbar)

    page.close()
    return pass1 + pass2


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
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser with a visible window (debugging)",
    )
    args = parser.parse_args()

    categories = [c.strip() for c in args.categories.split(",") if c.strip()]

    print("=" * 60)
    print("ListIQ — eBay Sold Listings Scraper (Playwright)")
    print("=" * 60)
    print(f"Categories: {categories}")
    print(f"Limit per category: {args.limit}")
    print(f"Output: {args.output}")
    print()

    all_data = []
    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=not args.headed)
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1440, "height": 900},
            locale="en-US",
        )

        for category in categories:
            print(f"Scraping: {category}")
            try:
                items = scrape_category(context, category, args.limit)
            except Exception as e:
                print(f"  ERROR scraping '{category}': {e}")
                items = []
            all_data.extend(items)
            print(f"  Got {len(items)} items\n")
            # Pause between categories
            time.sleep(random.uniform(3.0, 5.0))

        context.close()
        browser.close()

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
