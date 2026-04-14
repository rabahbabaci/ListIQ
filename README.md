# ListIQ — Cross-Platform Resale Intelligence Engine

**"Should I Sell This?"** — A seller intelligence module that tells resale sellers where to list, at what price, and whether it's worth their time, using real sold-listing data from eBay, Poshmark, and Depop.

Built for [Phia](https://phia.com/) as a capstone project for Data 198: Fashion x Data Science, UC Berkeley Spring 2026.

## Team

- Rabah Babaci
- Lisa Hao
- Perla Perez

## What's in this repo

```
listiq-backend/
├── scrapers/                  # Platform scraping + data cleaning scripts
│   ├── ebay_scraper.py        #   Playwright scraper for eBay completed listings
│   ├── poshmark_scraper.py    #   Poshmark public API scraper
│   ├── depop_scraper_v2.py    #   Depop scraper (curl_cffi for Cloudflare)
│   ├── clean_data.py          #   Per-platform data cleaning
│   └── merge_data.py          #   Merge into unified all_platforms.csv
├── data/
│   ├── raw/                   #   Raw scraper output (gitignored)
│   └── cleaned/               #   Cleaned CSVs + unified all_platforms.csv (committed)
├── notebooks/
│   ├── 01_eda.ipynb           #   Exploratory data analysis (Sprint 2)
│   ├── 02_pricing_model.ipynb #   XGBoost pricing model (Sprint 3)
│   ├── 03_routing_evaluation.ipynb  # Router validation (Sprint 4)
│   ├── 04_polished_figures.ipynb    # Presentation-quality figures (Sprint 6)
│   └── figures/               #   Generated figures (original + final/)
├── models/
│   ├── router.py              #   Platform routing algorithm (Sprint 4)
│   ├── README.md              #   Model docs, assumptions, evaluation
│   ├── pricing_model.joblib   #   Trained model (gitignored — regenerate from notebook 02)
│   └── feature_config.joblib  #   Feature engineering config (gitignored)
├── demo/
│   ├── fixtures/              #   16 pre-computed JSON fixtures for frontend (Sprint 5)
│   └── README.md              #   Demo docs with pitch script
├── scripts/
│   ├── compute_router_constants.py  # Regenerate price spread ratios from data
│   └── generate_demo_fixtures.py    # Regenerate demo JSON fixtures
├── research/                  # Research notes (placeholder)
├── requirements.txt
├── CLAUDE.md                  # AI assistant context and project conventions
└── README.md
```

## Pipeline overview

```
Scrape → Clean → Merge → EDA → Model → Route → Demo Fixtures
```

1. **Data collection** (Sprint 1) — Scraped 5,919 sold listings across 8 clothing categories from eBay (Playwright), Poshmark (public API), and Depop (curl_cffi)
2. **EDA** (Sprint 2) — Platform-fit hypothesis tests, true cost of reselling, "don't sell" analysis, sell-velocity patterns
3. **Pricing model** (Sprint 3) — XGBoost regression predicting sale price per platform (MAE $53, MedAPE 50%)
4. **Platform routing** (Sprint 4) — `recommend_listing()` ranks platforms by fit score, computes price tiers, net profit, and Worth It verdict
5. **Demo fixtures** (Sprint 5) — 16 curated JSON outputs for the Lovable frontend demo
6. **Polish** (Sprint 6/7) — Presentation-quality figures, documentation, reproducibility

## Setup

```bash
pip install -r requirements.txt
playwright install chromium    # required by the eBay scraper
```

## Reproducing the analysis

The cleaned dataset (`data/cleaned/all_platforms.csv`) is committed, so you can skip data collection and jump straight to analysis.

```bash
# 1. Train the pricing model (required before router or demo fixtures work)
#    Open and run: notebooks/02_pricing_model.ipynb
#    This generates: models/pricing_model.joblib, models/feature_config.joblib

# 2. Validate the router
#    Open and run: notebooks/03_routing_evaluation.ipynb

# 3. Generate demo fixtures
python scripts/generate_demo_fixtures.py

# 4. Generate presentation figures
#    Open and run: notebooks/04_polished_figures.ipynb
```

**Estimated runtimes:** Notebook 01 ~30s, Notebook 02 ~2min (GridSearchCV), Notebook 03 ~10s, Notebook 04 ~30s, fixture generation ~5s.

### Refreshing data from scratch

Only needed if you want to re-scrape (not required for analysis):

```bash
python scrapers/ebay_scraper.py
python scrapers/poshmark_scraper.py
# python scrapers/depop_scraper_v2.py   # may hit Cloudflare rate limits

python scrapers/clean_data.py --input data/raw/<platform>_sold_listings.csv \
                              --output data/cleaned/<platform>_cleaned.csv
python scrapers/merge_data.py
```

## Data schema

All cleaned CSVs share these columns:

| Field | Type | Notes |
|-------|------|-------|
| platform | str | eBay, Poshmark, or Depop |
| item_category | str | 8 categories (denim jacket, sneakers, handbag, etc.) |
| brand | str | Brand name or null |
| condition | str | New, Like New, Good, or Unknown |
| final_sale_price | float | Sold price (eBay/Poshmark) or listed price (Depop) |
| original_list_price | float | Null for eBay rows |
| days_to_sale | int | Poshmark only; null for eBay and Depop |
| sold_date | date | Null for Depop |
| title | str | Full listing title |
| item_id | str | Platform-specific ID |

The merged `all_platforms.csv` adds: `price_discount_pct`, `price_tier` (budget/mid/premium/luxury).

## Known limitations

- **Depop prices are listed, not sold.** Depop does not expose sold-price history publicly. All Depop figures are labeled "listed-price proxy."
- **eBay has no sell-velocity data.** The search-results page doesn't expose listing dates. Velocity estimates for eBay use a documented 0.75x multiplier on Poshmark data.
- **Luxury items have high model uncertainty.** MAE is $339 for items >$200 (vs. $17 for mid-tier).
- **Brand coverage is long-tail.** 595 of 712 brands have <5 items and are treated as "Unknown."
- **Depop covers 4 of 8 categories** due to Cloudflare rate-limiting during the initial scrape.
