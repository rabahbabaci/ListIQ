# ListIQ Demo Fixtures

Pre-computed JSON outputs from `recommend_listing()` for the Lovable frontend demo. Each fixture is a full platform routing recommendation for a curated resale item.

## Consuming fixtures

```
demo/fixtures/
├── index.json           # manifest with all items + metadata
├── levis-denim-jacket.json
├── nike-sneakers.json
└── ... (16 total)
```

**Frontend workflow:**
1. Fetch `index.json` for the item list (id, category, brand, verdict, best platform)
2. Load individual `{demo_item_id}.json` for the full recommendation response
3. Each fixture contains the locked API contract (`item`, `recommendations`, `worth_it`) plus two metadata fields: `demo_item_id` and `demo_narrative_purpose`

## Demo items

| # | Item | Best Platform | $/hr | Verdict | Purpose |
|---|------|--------------|------|---------|---------|
| 1 | Levi's denim jacket, Like New | eBay | $60 | true | Brand recognition opener |
| 2 | Nike sneakers, New | eBay | $87 | true | Mass-market brand, high confidence |
| 3 | Jordan sneakers, Like New | eBay | $133 | true | Premium sneaker, highest ROI |
| 4 | Louis Vuitton handbag, Like New | eBay | $473 | true | Luxury showcase (see caveat below) |
| 5 | Coach crossbody bag, Like New | eBay | $119 | true | Premium accessory |
| 6 | Anthropologie midi dress, Like New | Poshmark | $54 | true | Poshmark wins — brand fit |
| 7 | Harley-Davidson vintage t-shirt, Good | eBay | $42 | true | Niche brand, collector appeal |
| 8 | Levi's leather jacket, Like New | eBay | $152 | true | High-value 2-way item |
| 9 | H&M midi dress, Good | Poshmark | $20 | marginal | Budget fast-fashion, "think twice" |
| 10 | Unknown blazer, Good | Poshmark | $13 | marginal | No brand, low confidence |
| 11 | Unknown midi dress, Good | Poshmark | $17 | marginal | Cheapest item, barely viable |
| 12 | Zara denim jacket, Good | eBay | $23 | true | Known brand, lower margin |
| 13 | Old Navy denim jacket, Good | Poshmark | $5 | **false** | **The "don't sell" punchline** |
| 14 | Unknown denim jacket, Good | eBay | $15 | marginal | Reinforces marginal zone |
| 15 | Coach handbag, Good | eBay | $67 | true | Surprising: eBay > Poshmark for Coach |
| 16 | Free People midi dress, New | Poshmark | $43 | true | Poshmark wins on brand-audience fit |

## Suggested demo script (pitch order)

### Act 1: "This works" (build confidence)

1. **Levi's denim jacket** — Open with a familiar brand. "$60/hr effective rate on eBay. The router explains why: eBay's larger buyer pool moves denim jackets faster."
2. **Nike sneakers** — Scale up. "$87/hr. eBay wins again for sneakers."
3. **Jordan sneakers** — Premium tier. "$133/hr. Brand tier matters — Jordan gets premium pricing."

### Act 2: "This is dramatic" (the wow moment)

4. **Louis Vuitton handbag** — Dramatic pause. "$473/hr. The luxury tier."
   - *If asked about accuracy:* "Our model's uncertainty is highest for luxury items (MAE $339 on items >$200). The directional recommendation is sound — eBay for luxury — but the exact dollar amount has a wide confidence interval. That's why we show price tiers: the fast-sale tier is more conservative."

### Act 3: "Platform choice matters" (routing insight)

5. **Anthropologie midi dress** — "Same model, different answer. Poshmark wins here — Anthropologie's audience shops on Poshmark."
6. **Coach crossbody bag** — "$119/hr on eBay."
7. **Coach handbag** — "Interesting — Coach crossbody goes to eBay too, even though Poshmark is known for Coach. The router considers category-level economics, not just brand affinity."

### Act 4: "The turn" (marginal territory)

8. **H&M midi dress** — "Now here's where it gets real. H&M midi dress: marginal. $20/hr. Think twice before photographing, writing a listing, packaging, and shipping this."
9. **Unknown blazer** — "$13/hr. No brand recognition, lower value category."

### Act 5: "The punchline" (don't sell)

10. **Old Navy denim jacket** — "This one? **Don't bother.** $5/hr effective rate. You'd make more money doing almost anything else. ListIQ's value isn't just telling you where to sell — it's telling you when *not* to sell."

### Close: "The full picture"

11. **Free People midi dress** — "Back to a winner. Poshmark, $43/hr. The platform routing is consistent for the right items."

*Remaining items (Harley-Davidson vintage tee, Levi's leather jacket, Zara denim jacket, Unknown items) are available for Q&A deep-dives or to demonstrate coverage across all 8 categories.*

## Key finding: Depop never wins rank 1

Across all 16 demo items (and 30+ tested candidates), Depop never achieves the top recommendation. This is structural:

- Depop's model predictions are lower because it was trained on **listed prices**, not confirmed sold prices
- Depop's estimated sell-through is slightly slower (1.1x Poshmark baseline)
- While Depop has the lowest fees (10%), the price and velocity disadvantages outweigh the fee savings

**This is an honest finding, not a bug.** Depop consistently ranks 2nd or 3rd, and the reasoning text explains why. If the panel asks, the answer is: "Our data shows Depop's lower fees don't compensate for its lower realized prices in any of our 8 categories."

## Luxury item caveat

The Louis Vuitton handbag ($473/hr, $324 balanced price) uses the same pricing model as all other items, but the model's accuracy on luxury items (>$200) is significantly lower:

- **Luxury tier MAE:** $339 (vs. $17 for mid-tier items)
- **Luxury tier MedAPE:** 75%

The directional recommendation (eBay for luxury handbags) is well-supported by the data. The specific dollar amounts should be treated as estimates with wide uncertainty bands. The price tiers (fast-sale through max-revenue) help communicate this range.

## Regenerating fixtures

After any model or router changes:

```bash
python scripts/generate_demo_fixtures.py
```

This clears `demo/fixtures/`, regenerates all 16 items, validates schemas, and prints a summary. Exit code is non-zero if any validation fails.
