# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ListIQ is a cross-platform resale intelligence engine ("Should I Sell This?") that scrapes sold-listing data from eBay, Poshmark, and Depop, then predicts optimal platform, price, and sell-through speed. Built as a UC Berkeley capstone project for Phia.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium   # required by the eBay scraper
```

## Running the pipeline

```bash
# 1. Scrape (each script is a standalone CLI: --categories, --limit, --output)
python scrapers/ebay_scraper.py
python scrapers/poshmark_scraper.py
# python scrapers/depop_scraper.py    # not built yet

# 2. Clean a raw CSV into the cleaned/ folder
python scrapers/clean_data.py --input data/raw/<platform>_sold_listings.csv \
                              --output data/cleaned/<platform>_cleaned.csv

# 3. Merge all per-platform cleaned files into the unified dataset
python scrapers/merge_data.py
```

Raw scraper output goes to `data/raw/` (gitignored). Cleaned per-platform datasets and the unified `all_platforms.csv` live in `data/cleaned/`.

## Architecture

**Pipeline:** Scrape → Clean → Merge → EDA → Model → Demo

- `scrapers/`
  - `ebay_scraper.py` — Playwright + `playwright-stealth` scraper of eBay's public completed/sold listings page (`LH_Complete=1&LH_Sold=1`). Two-pass collection per category (recency sort + lowest-price sort, deduped on `item_id`) to broaden `sold_date` coverage.
  - `poshmark_scraper.py` — Hits Poshmark's public category HTML pages for listing IDs, then `/vm-rest/posts/{id}` for structured data. No API key needed.
  - `clean_data.py` — Per-platform cleaner: drops zero/null prices, nulls junk `original_list_price`, caps `days_to_sale` at 365, regex-parses condition from titles, normalizes brand variants via `BRAND_ALIASES`.
  - `merge_data.py` — Reads every `*_cleaned.csv` in `data/cleaned/` (no hardcoded platform list — new platforms auto-include), drops `final_sale_price < $1`, normalizes condition as a safety net, adds `price_discount_pct` and `price_tier`, writes `all_platforms.csv`.
- `data/raw/` — Gitignored raw CSVs from scrapers.
- `data/cleaned/` — Per-platform cleaned CSVs + `all_platforms.csv` (unified, used for EDA/modeling).
- `models/` — Trained model artifacts (gitignored `.pkl`/`.joblib`/`.h5`).
- `notebooks/` — Jupyter notebooks for EDA and experimentation.
- `demo/` — Streamlit app for the seller intelligence report.
- `demo/fixtures/` — Pre-computed JSON outputs from `recommend_listing()` for the Lovable frontend demo. Regenerate with `python scripts/generate_demo_fixtures.py`.
- `scripts/` — Utility scripts: `compute_router_constants.py` (price spread ratios), `generate_demo_fixtures.py` (demo JSON fixtures).

## Shared schema

Every per-platform cleaned CSV and `all_platforms.csv` shares these columns:

`platform, item_category, brand, condition, final_sale_price, original_list_price, days_to_sale, listing_day_of_week, listing_time, sold_date, title, item_id, image_url, days_to_sale_outlier`

The merged file additionally has: `price_discount_pct`, `price_tier` (`budget` <$20, `mid` $20–75, `premium` $75–200, `luxury` >$200).

## Known data characteristics

- **eBay rows have null `days_to_sale`, `listing_day_of_week`, `listing_time`, and `original_list_price`** — eBay's search-results card layout doesn't expose listing dates or strikethrough prices. Recovering them would require visiting each listing detail page. `price_discount_pct` is therefore null for all eBay rows.
- **eBay scraper currently captures auction starting bids** ($0.99) for unbid auctions because it parses the search-card price. The merge step's `< $1` floor drops these (~90 rows on the current 4k scrape), but the proper fix is to add `LH_BIN=1` (Buy It Now only) to the eBay search URL — pending follow-up.
- **Brand extraction on eBay uses a hardcoded known-brand list** in `ebay_scraper.py` (~150 entries, matched with non-letter lookarounds + curly-quote normalization). Long tail of small brands → "Unknown" rate is ~60% on eBay. Poshmark uses the platform's structured `brand` field directly.
- **Depop rows have null `condition`** — Depop renders condition via a client-side React lazy component that fetches from an authenticated API after page hydration. It does not appear in either the search-page or detail-page HTML payloads, so the public-web scraper (`depop_scraper_v2.py`) cannot reach it without an authenticated session or running real JS via Playwright.
- **Depop's `final_sale_price` is the LISTED price, not a sold price.** Depop does not expose sold history publicly. Treat Depop rows as "listed price / market positioning" rather than "what items actually sold for." This is the same reason the original eBay API path was abandoned in favor of the completed-listings page scrape. Downstream modeling should be aware that Depop and eBay/Poshmark are not directly comparable on the price column.
- **Depop scraper requires `curl_cffi`** (Chrome TLS impersonation) because Depop is fronted by Cloudflare and 403s plain `requests` / `urllib3` based on TLS fingerprint. `curl_cffi>=0.7.0` is in `requirements.txt`.
- **Depop covers only 4 of 8 categories** due to Cloudflare rate-limiting partway through the initial scrape. After ~819 successful detail-page hits the session began returning 403s on every request. The block is IP+rate based, not session/cookie based, so resetting the curl_cffi session does not help — only longer pacing or waiting it out would. Coverage as shipped:
  - ✅ Complete: `denim jacket` (250), `midi dress` (250), `sneakers` (250)
  - ⚠ Partial: `handbag` (69)
  - ❌ Not collected: `blazer`, `vintage t-shirt`, `leather jacket`, `crossbody bag` (Poshmark + eBay only)
  - **Cross-platform analysis should focus on the 4 fully-covered categories** (denim jacket, midi dress, sneakers, handbag) for the most robust three-way comparisons. The other 4 categories remain two-platform (Poshmark + eBay).

## Sprint 1 status

- ✅ #2 eBay scraper (Playwright completed-listings rewrite)
- ✅ #5 Poshmark handbag backfill (handbag 48 → 190)
- ✅ #4 Cross-platform merge script
- ✅ #3 Depop scraper (API + curl_cffi, 4 of 8 categories — see "Known data characteristics")
- ⏳ #7 True Cost of Reselling — research, no-code

Current dataset (post-merge): **5,919 rows** = 3,910 eBay + 1,190 Poshmark + 819 Depop, across 8 categories (Depop covers 4 of 8).
