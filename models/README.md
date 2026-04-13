# ListIQ Pricing Model

## Overview

XGBoost regression model predicting `final_sale_price` for resale items across eBay, Poshmark, and Depop. Trained on 4,735 rows (80% of 5,919 unified dataset), tested on 1,184 rows.

- **Target:** `log1p(final_sale_price)` — predictions inverted with `expm1`
- **Architecture:** One unified model with `platform` as a feature
- **Training notebook:** `notebooks/02_pricing_model.ipynb`

## Files

| File | Description |
|------|-------------|
| `pricing_model.joblib` | Serialized sklearn Pipeline (preprocessor + XGBoost) |
| `feature_config.joblib` | Brand lists, condition map, feature column names |

## Loading the model

```python
import joblib
import numpy as np

model = joblib.load("models/pricing_model.joblib")
config = joblib.load("models/feature_config.joblib")
```

## Making predictions

The model expects a DataFrame with these columns:

**Categorical:** `platform`, `item_category`, `brand_tier`, `brand_top30`, `condition`, `platform_category`

**Numeric:** `condition_ordinal`, `title_length`, `title_word_count`, `title_has_brand`, `title_has_size`, `title_has_vintage`, `title_has_nwt`

Use the `engineer_features()` function in `notebooks/02_pricing_model.ipynb` to build these from raw inputs (`platform`, `item_category`, `brand`, `condition`, `title`).

```python
pred_log = model.predict(features_df)
pred_price = np.clip(np.expm1(pred_log), 1.0, None)
```

## Performance (test set)

| Model | MAE ($) | RMSE ($) | MedAPE (%) |
|-------|---------|----------|------------|
| Baseline (group median) | $61.17 | $182.38 | 57.0% |
| Ridge | $54.16 | $158.29 | 51.1% |
| **XGBoost (tuned)** | **$52.79** | **$151.16** | **50.2%** |

### Per-platform

| Platform | MAE ($) | MedAPE (%) | n |
|----------|---------|------------|---|
| eBay | $60.01 | 50.5% | 782 |
| Poshmark | $44.20 | 46.0% | 238 |
| Depop (listed price proxy) | $30.85 | 51.6% | 164 |

Platform parity: 1.9x MAE spread — reasonable.

### Per-price-tier

| Tier | MAE ($) | MedAPE (%) | n |
|------|---------|------------|---|
| Budget (<$20) | $16.39 | 124.3% | 373 |
| Mid ($20-75) | $17.15 | 32.0% | 530 |
| Premium ($75-200) | $72.75 | 55.8% | 180 |
| Luxury (>$200) | $338.71 | 75.1% | 101 |

## Caveats

1. **Depop predictions are listed-price proxies**, not sold-price predictions. Depop does not expose sold-price history.
2. **Luxury items (>$200)** have high MAE ($339) due to variance and thin data.
3. **Budget items** have high MedAPE (124%) because small absolute errors produce large percentage errors on low-price items.
4. **595/712 brands** have <5 items and are treated as "unknown." Brand signal comes from top 30 brands + tier classification.
5. **No photo features, no temporal features.** Visual condition and seasonality are not captured.

## Best hyperparameters

```
max_depth: 4
learning_rate: 0.05
n_estimators: 300
min_child_weight: 5
subsample: 1.0
```

## Top features

1. `brand_tier_luxury` — dominant signal
2. `brand_tier_premium`
3. `platform_category_eBay_leather jacket`
4. `item_category_sneakers`
5. `item_category_leather jacket`
