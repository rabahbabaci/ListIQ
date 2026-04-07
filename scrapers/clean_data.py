"""
ListIQ — Data Cleaning Pipeline
================================
Takes raw scraped CSVs and outputs cleaned, normalized datasets.

Usage:
    python scrapers/clean_data.py
    python scrapers/clean_data.py --input data/raw/poshmark_sold_listings.csv --output data/cleaned/poshmark_cleaned.csv
"""

import re
import argparse
from pathlib import Path

import pandas as pd
import numpy as np


# Brand alias map — collapse common variant spellings to a single canonical
# brand. Applied to all platforms in `clean()`. Lookup is case-insensitive on
# the alias key but the canonical value is preserved exactly.
BRAND_ALIASES = {
    "levis": "Levi's",
    "levi": "Levi's",
    "levi strauss": "Levi's",
    "levi strauss & co": "Levi's",
    "lauren ralph lauren": "Ralph Lauren",
    "polo ralph lauren": "Ralph Lauren",
    "polo by ralph lauren": "Ralph Lauren",
    "lauren": "Ralph Lauren",
    "tommy": "Tommy Hilfiger",
    "tommy jeans": "Tommy Hilfiger",
    "ck": "Calvin Klein",
    "calvin klein jeans": "Calvin Klein",
    "ysl": "Saint Laurent",
    "yves saint laurent": "Saint Laurent",
    "louis vuitton lv": "Louis Vuitton",
    "lv": "Louis Vuitton",
    "dr martens": "Dr. Martens",
    "doc martens": "Dr. Martens",
    "the north face": "The North Face",
    "north face": "The North Face",
    "harley davidson": "Harley-Davidson",
    "abercrombie": "Abercrombie & Fitch",
    "j crew": "J.Crew",
    "alo": "Alo Yoga",
    "ag jeans": "AG Jeans",
    "ag adriano goldschmied": "AG Jeans",
    "stüssy": "Stussy",
    "comme des garçons": "Comme des Garcons",
    "cdg": "Comme des Garcons",
    "off white": "Off-White",
    "a bathing ape": "Bape",
    "aimé leon dore": "Aime Leon Dore",
    "hermès": "Hermes",
    "christian dior": "Dior",
    "arc'teryx": "Arcteryx",
    "ll bean": "L.L. Bean",
    "g star raw": "G-Star",
    "g-star raw": "G-Star",
    "st. john": "St John",
}


# Brand values that platforms emit as a "no real brand" placeholder.
# Treat these as missing so downstream modeling doesn't see them as a real brand.
BRAND_PLACEHOLDERS = {"other", "unknown", "n/a", "none", "no brand", "unbranded"}


def normalize_brand(brand):
    """Map brand variants to a canonical form.

    Case-insensitive on the alias key. Strips leading/trailing whitespace and
    normalizes curly quotes/apostrophes before lookup. Platform placeholder
    values like "Other" / "Unknown" / "Unbranded" are mapped to NaN so they
    aren't treated as real brands. Unknown (real) brands pass through unchanged.
    """
    if not isinstance(brand, str):
        return brand
    cleaned = brand.strip().replace("\u2019", "'").replace("\u2018", "'")
    if not cleaned:
        return np.nan
    key = cleaned.lower().rstrip(".")
    if key in BRAND_PLACEHOLDERS:
        return np.nan
    return BRAND_ALIASES.get(key, cleaned)


# Condition keyword patterns, checked in priority order.
# First match wins — e.g. "NWOT" matches before "NWT" because it's checked first.
CONDITION_PATTERNS = [
    (r"\bNWOT\b|new without tags", "Like New"),
    (r"\bNWT\b|new with tags|\bbrand new\b|\bNEW\b", "New"),
    (r"\bEUC\b|excellent\s+(used\s+)?condition", "Like New"),
    (r"\bVGUC\b|very good (used )?condition", "Good"),
    (r"\bGUC\b|gently used|good (used )?condition", "Good"),
    (r"\bfair\b|well worn|signs of wear", "Fair"),
    (r"\blike new\b|\bmint\b", "Like New"),
    (r"\bpre[- ]?owned\b|\bused\b", "Good"),
]


def parse_condition(title):
    """Extract condition from listing title using keyword matching.

    Returns the mapped condition string, or None if no keywords found.
    """
    if not isinstance(title, str):
        return None
    for pattern, condition in CONDITION_PATTERNS:
        if re.search(pattern, title, re.IGNORECASE):
            return condition
    return None


def clean(df):
    """Apply all cleaning rules to a DataFrame of raw listings."""
    original_len = len(df)

    # 1. Drop rows where final_sale_price is 0 or null
    df = df[df["final_sale_price"].notna() & (df["final_sale_price"] > 0)].copy()
    dropped_price = original_len - len(df)

    # 2. Set original_list_price to null where 0 or >= 999
    bad_orig = (df["original_list_price"] == 0) | (df["original_list_price"] >= 999)
    df.loc[bad_orig, "original_list_price"] = np.nan

    # 3. Cap days_to_sale at 365, flag outliers
    df["days_to_sale_outlier"] = df["days_to_sale"] > 365
    df["days_to_sale"] = df["days_to_sale"].clip(upper=365)

    # 4. Parse condition from title
    parsed = df["title"].apply(parse_condition)
    # Only overwrite "Unknown" conditions; keep any already-set values.
    # Cast to object first — when condition starts as all-null (e.g. Depop,
    # which doesn't expose condition publicly), the column is inferred as
    # float64 and a partial string assignment via .loc raises a pandas
    # FutureWarning about incompatible dtypes.
    df["condition"] = df["condition"].astype(object)
    unknown_mask = (df["condition"] == "Unknown") | df["condition"].isna()
    df.loc[unknown_mask & parsed.notna(), "condition"] = parsed[unknown_mask & parsed.notna()]

    # 5. Normalize brand variants (Levis → Levi's, etc.)
    if "brand" in df.columns:
        df["brand"] = df["brand"].apply(normalize_brand)

    return df, dropped_price


def print_summary(df, dropped_price):
    """Print a summary of the cleaned dataset."""
    print("=" * 60)
    print("Cleaning Summary")
    print("=" * 60)
    print(f"Rows dropped (price = 0 or null): {dropped_price}")
    print(f"Rows remaining: {len(df)}")
    print()

    print("--- Category Breakdown ---")
    for cat, count in df["item_category"].value_counts().sort_index().items():
        print(f"  {cat}: {count}")
    print()

    print("--- Condition Distribution ---")
    cond_counts = df["condition"].value_counts()
    for cond, count in cond_counts.items():
        print(f"  {cond}: {count} ({count / len(df) * 100:.1f}%)")
    print()

    print("--- Price Stats ---")
    print(f"  final_sale_price:    median=${df['final_sale_price'].median():.0f}, mean=${df['final_sale_price'].mean():.0f}")
    orig = df["original_list_price"].dropna()
    print(f"  original_list_price: median=${orig.median():.0f}, mean=${orig.mean():.0f} ({df['original_list_price'].isna().sum()} nulled out)")
    print()

    print("--- Days to Sale ---")
    print(f"  median={df['days_to_sale'].median():.0f}, mean={df['days_to_sale'].mean():.0f}")
    print(f"  Capped at 365: {df['days_to_sale_outlier'].sum()} rows flagged as outliers")
    print()

    print("--- Nulls ---")
    for col in ["brand", "condition", "original_list_price", "sold_date"]:
        nulls = df[col].isna().sum()
        print(f"  {col}: {nulls} ({nulls / len(df) * 100:.1f}%)")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Clean raw ListIQ scraped data")
    parser.add_argument(
        "--input",
        type=str,
        default="data/raw/poshmark_sold_listings.csv",
        help="Input raw CSV path",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/cleaned/poshmark_cleaned.csv",
        help="Output cleaned CSV path",
    )
    args = parser.parse_args()

    print(f"Reading: {args.input}")
    df = pd.read_csv(args.input)
    print(f"Raw rows: {len(df)}")
    print()

    df, dropped_price = clean(df)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Saved cleaned data to: {args.output}")
    print()

    print_summary(df, dropped_price)


if __name__ == "__main__":
    main()
