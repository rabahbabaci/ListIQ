"""Generate pre-computed JSON fixtures from recommend_listing() for the Lovable frontend demo.

Usage:
    python scripts/generate_demo_fixtures.py

Clears demo/fixtures/, generates one JSON file per curated demo item,
writes an index.json manifest, and validates every output against the
locked API contract. Exits non-zero if any validation fails.
"""

import json
import math
import re
import shutil
import sys
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.router import recommend_listing

# ---------------------------------------------------------------------------
# Curated demo items (16 items)
# ---------------------------------------------------------------------------

DEMO_ITEMS = [
    # --- Clear YES (8 items) ---
    {
        "item": {
            "category": "denim jacket",
            "brand": "Levi's",
            "condition": "Like New",
            "size": "M",
            "color": "blue",
            "estimated_retail": 89.99,
        },
        "narrative_purpose": "Brand recognition opener — clear worth-it",
    },
    {
        "item": {
            "category": "sneakers",
            "brand": "Nike",
            "condition": "New",
            "size": "10",
            "color": "white",
            "estimated_retail": 120.00,
        },
        "narrative_purpose": "Mass-market brand, high confidence routing",
    },
    {
        "item": {
            "category": "sneakers",
            "brand": "Jordan",
            "condition": "Like New",
            "size": "11",
            "color": "red",
            "estimated_retail": 190.00,
        },
        "narrative_purpose": "Premium sneaker, highest sneaker ROI",
    },
    {
        "item": {
            "category": "handbag",
            "brand": "Louis Vuitton",
            "condition": "Like New",
            "size": "OS",
            "color": "brown",
            "estimated_retail": 2000.00,
        },
        "narrative_purpose": "Luxury showcase — dramatic $/hr (note: luxury tier has high model uncertainty, MAE $339)",
    },
    {
        "item": {
            "category": "crossbody bag",
            "brand": "Coach",
            "condition": "Like New",
            "size": "OS",
            "color": "tan",
            "estimated_retail": 250.00,
        },
        "narrative_purpose": "Premium accessory, strong eBay routing",
    },
    {
        "item": {
            "category": "midi dress",
            "brand": "Anthropologie",
            "condition": "Like New",
            "size": "M",
            "color": "floral",
            "estimated_retail": 148.00,
        },
        "narrative_purpose": "Poshmark wins — brand-audience fit",
    },
    {
        "item": {
            "category": "vintage t-shirt",
            "brand": "Harley-Davidson",
            "condition": "Good",
            "size": "L",
            "color": "black",
            "estimated_retail": 45.00,
        },
        "narrative_purpose": "2-way category, niche brand with collector appeal",
    },
    {
        "item": {
            "category": "leather jacket",
            "brand": "Levi's",
            "condition": "Like New",
            "size": "M",
            "color": "brown",
            "estimated_retail": 200.00,
        },
        "narrative_purpose": "High-value 2-way item, strong premium signal",
    },
    # --- Marginal (4 items) ---
    {
        "item": {
            "category": "midi dress",
            "brand": "H&M",
            "condition": "Good",
            "size": "S",
            "color": "black",
            "estimated_retail": 24.99,
        },
        "narrative_purpose": "Budget fast-fashion — marginal, 'think twice' moment",
    },
    {
        "item": {
            "category": "blazer",
            "brand": "Unknown",
            "condition": "Good",
            "size": "L",
            "color": "gray",
            "estimated_retail": 40.00,
        },
        "narrative_purpose": "No brand signal, low confidence — marginal verdict",
    },
    {
        "item": {
            "category": "midi dress",
            "brand": "Unknown",
            "condition": "Good",
            "size": "L",
            "color": "gray",
            "estimated_retail": 15.00,
        },
        "narrative_purpose": "Cheapest item in demo — barely above threshold",
    },
    {
        "item": {
            "category": "denim jacket",
            "brand": "Zara",
            "condition": "Good",
            "size": "S",
            "color": "light wash",
            "estimated_retail": 49.99,
        },
        "narrative_purpose": "Known brand but low margin category — marginal zone",
    },
    # --- Clear NO (2 items) ---
    {
        "item": {
            "category": "denim jacket",
            "brand": "Old Navy",
            "condition": "Good",
            "size": "M",
            "color": "blue",
            "estimated_retail": 35.00,
        },
        "narrative_purpose": "THE 'don't sell' punchline — $5/hr, not worth your time",
    },
    {
        "item": {
            "category": "denim jacket",
            "brand": "Unknown",
            "condition": "Good",
            "size": "L",
            "color": "black",
            "estimated_retail": 30.00,
        },
        "narrative_purpose": "Reinforces don't-sell — unknown brand, low value category",
    },
    # --- Cross-platform variety (2 items) ---
    {
        "item": {
            "category": "handbag",
            "brand": "Coach",
            "condition": "Good",
            "size": "OS",
            "color": "black",
            "estimated_retail": 350.00,
        },
        "narrative_purpose": "Surprising routing — eBay beats Poshmark for Coach (Poshmark is known for Coach)",
    },
    {
        "item": {
            "category": "midi dress",
            "brand": "Free People",
            "condition": "New",
            "size": "S",
            "color": "white",
            "estimated_retail": 128.00,
        },
        "narrative_purpose": "Poshmark wins again — brand-audience alignment",
    },
]


# ---------------------------------------------------------------------------
# Schema validation (reused from Sprint 4 evaluation)
# ---------------------------------------------------------------------------

EXPECTED_ITEM_KEYS = {"category", "brand", "size", "condition", "color", "estimated_retail"}
EXPECTED_REC_KEYS = {
    "platform", "rank", "fit_score", "price_tiers", "platform_fee_pct",
    "estimated_shipping", "net_profit", "estimated_time_minutes",
    "effective_hourly_rate", "sell_probability_30d", "estimated_days_to_sale",
    "reasoning",
}
EXPECTED_TIER_KEYS = {"fast_sale", "balanced", "max_revenue"}
EXPECTED_WORTH_IT_KEYS = {
    "verdict", "best_net_profit", "best_platform",
    "effective_hourly_rate", "explanation",
}


def validate_response(response: dict) -> list[str]:
    """Return list of schema violations (empty = valid)."""
    errors = []

    # Top-level keys (allow demo metadata alongside contract keys)
    contract_keys = {"item", "recommendations", "worth_it"}
    if not contract_keys.issubset(response.keys()):
        errors.append(f"Missing top-level keys: {contract_keys - set(response.keys())}")

    # Item block
    item = response.get("item", {})
    if set(item.keys()) != EXPECTED_ITEM_KEYS:
        errors.append(f"Item keys: got {set(item.keys())}, expected {EXPECTED_ITEM_KEYS}")

    # Recommendations
    recs = response.get("recommendations", [])
    if len(recs) != 3:
        errors.append(f"Expected 3 recommendations, got {len(recs)}")

    platforms_seen = set()
    for i, rec in enumerate(recs):
        if set(rec.keys()) != EXPECTED_REC_KEYS:
            errors.append(f"Rec[{i}] keys mismatch")
        if rec.get("rank") != i + 1:
            errors.append(f"Rec[{i}] rank should be {i + 1}, got {rec.get('rank')}")
        for tier_field in ["price_tiers", "net_profit"]:
            tiers = rec.get(tier_field, {})
            if set(tiers.keys()) != EXPECTED_TIER_KEYS:
                errors.append(f"Rec[{i}].{tier_field} keys mismatch")
            for k, v in tiers.items():
                if v is None or (isinstance(v, float) and math.isnan(v)):
                    errors.append(f"Rec[{i}].{tier_field}.{k} is null/NaN")
        if not isinstance(rec.get("reasoning"), str) or len(rec.get("reasoning", "")) < 10:
            errors.append(f"Rec[{i}] reasoning too short or wrong type")
        fs = rec.get("fit_score", -1)
        if not (0 <= fs <= 10):
            errors.append(f"Rec[{i}] fit_score {fs} outside [0, 10]")
        platforms_seen.add(rec.get("platform"))

    if len(platforms_seen) != 3:
        errors.append(f"Expected 3 distinct platforms, got {platforms_seen}")

    # Worth it
    worth = response.get("worth_it", {})
    if set(worth.keys()) != EXPECTED_WORTH_IT_KEYS:
        errors.append(f"worth_it keys mismatch")
    if worth.get("verdict") not in (True, False, "marginal"):
        errors.append(f"worth_it.verdict unexpected: {worth.get('verdict')}")

    # Cross-checks
    if recs:
        if worth.get("best_platform") != recs[0].get("platform"):
            errors.append("worth_it.best_platform != rank-1 platform")
        expected_hourly = round(
            recs[0].get("net_profit", {}).get("balanced", 0) / (35 / 60), 2
        )
        actual_hourly = worth.get("effective_hourly_rate", 0)
        if abs(actual_hourly - expected_hourly) > 0.02:
            errors.append(
                f"Hourly rate mismatch: worth_it says {actual_hourly}, "
                f"computed {expected_hourly}"
            )

    return errors


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slugify(item: dict) -> str:
    """Generate a slug from brand + category."""
    brand = item.get("brand", "unknown").lower()
    brand = brand.replace("&", "and").replace("'", "")
    category = item.get("category", "").lower()
    raw = f"{brand}-{category}"
    return re.sub(r"[^a-z0-9]+", "-", raw).strip("-")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    fixtures_dir = Path(__file__).resolve().parent.parent / "demo" / "fixtures"

    # Clear and recreate
    if fixtures_dir.exists():
        shutil.rmtree(fixtures_dir)
    fixtures_dir.mkdir(parents=True)

    index = []
    all_valid = True
    failed_items = []

    print(f"Generating {len(DEMO_ITEMS)} demo fixtures...\n")
    header = f"{'#':<3} {'Slug':<35} {'#1 Platform':<12} {'Bal$':<8} {'$/hr':<8} {'Verdict':<10} {'Valid'}"
    print(header)
    print("-" * len(header))

    for i, entry in enumerate(DEMO_ITEMS):
        item = entry["item"]
        narrative = entry["narrative_purpose"]

        # Generate recommendation
        result = recommend_listing(item)

        # Add demo metadata
        slug = slugify(item)
        result["demo_item_id"] = slug
        result["demo_narrative_purpose"] = narrative

        # Validate
        errors = validate_response(result)
        valid = len(errors) == 0
        if not valid:
            all_valid = False
            failed_items.append((slug, errors))

        # Write fixture
        fixture_path = fixtures_dir / f"{slug}.json"
        with open(fixture_path, "w") as f:
            json.dump(result, f, indent=2)

        # Index entry
        best = result["recommendations"][0]
        worth = result["worth_it"]
        index.append({
            "demo_item_id": slug,
            "narrative_purpose": narrative,
            "category": item["category"],
            "brand": item.get("brand", "Unknown"),
            "best_platform": best["platform"],
            "verdict": worth["verdict"],
        })

        # Print row
        icon = "\u2705" if valid else "\u274c"
        print(
            f"{i+1:<3} {slug:<35} {best['platform']:<12} "
            f"${best['price_tiers']['balanced']:<7} "
            f"${worth['effective_hourly_rate']:<7.0f} "
            f"{str(worth['verdict']):<10} {icon}"
        )

    # Write index
    index_path = fixtures_dir / "index.json"
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"Fixtures written to: {fixtures_dir}/")
    print(f"Total items: {len(DEMO_ITEMS)}")
    print(f"Index: {index_path}")

    verdicts = [e["verdict"] for e in index]
    print(f"\nVerdict breakdown:")
    print(f"  True:     {verdicts.count(True)}")
    print(f"  Marginal: {verdicts.count('marginal')}")
    print(f"  False:    {verdicts.count(False)}")

    platforms = [e["best_platform"] for e in index]
    print(f"\nPlatform winners:")
    for p in ["eBay", "Poshmark", "Depop"]:
        print(f"  {p}: {platforms.count(p)}")

    if all_valid:
        print(f"\n\u2705 All {len(DEMO_ITEMS)} fixtures pass schema validation")
    else:
        print(f"\n\u274c {len(failed_items)} fixture(s) FAILED validation:")
        for slug, errs in failed_items:
            print(f"  {slug}:")
            for e in errs:
                print(f"    - {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
