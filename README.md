# ListIQ — Cross-Platform Resale Intelligence Engine

**"Should I Sell This?"** — A seller intelligence module that tells resale sellers where to list, at what price, and how fast an item will sell, using real sold-listing data across platforms.

Built for [Phia](https://phia.com/) as a capstone project for Data 198: Fashion x Data Science, UC Berkeley Spring 2026.

## Team
- Rabah Babaci
- Lisa Hao
- Perla Perez
- Alex Thomas Suggs

## Project Structure

```
listiq-repo/
├── scrapers/          # Platform scraping scripts (eBay, Poshmark, Depop)
├── data/
│   ├── raw/           # Raw scraped data (not committed — see .gitignore)
│   └── cleaned/       # Normalized, cleaned datasets
├── models/            # Trained model artifacts and evaluation notebooks
├── notebooks/         # EDA, analysis, and experimentation notebooks
├── demo/              # Streamlit/Gradio demo application
├── requirements.txt   # Python dependencies
└── README.md
```

## Pipeline Overview

1. **Data Collection** — Scrape sold listings from eBay (API), Poshmark, and Depop
2. **EDA + Segmentation** — Platform-item fit analysis, price distributions, sell velocity patterns
3. **Predictive Modeling** — Price prediction (regression) + sell-through probability (classification)
4. **Platform Routing** — Composite scoring algorithm ranking platforms per item type
5. **Demo** — Upload a photo → get a seller intelligence report

## Setup

```bash
pip install -r requirements.txt
```

## Data Schema

All sold-listing data is normalized into:

| Field | Type | Description |
|-------|------|-------------|
| platform | str | eBay, Poshmark, or Depop |
| item_category | str | e.g., denim jacket, midi dress, sneakers |
| brand | str | Brand name |
| condition | str | New, Like New, Good, Fair |
| final_sale_price | float | Actual sold price (USD) |
| original_list_price | float | Original asking price (USD) |
| days_to_sale | int | Days from listing to sale |
| listing_day_of_week | str | Day item was listed |
| listing_time | str | Time of day listed |
| sold_date | date | Date the item sold |

## Contributing

### First time setup

```bash
git clone https://github.com/rabahbabaci/ListIQ.git
cd ListIQ
python -m venv venv
source venv/bin/activate        # Mac/Linux
# venv\Scripts\activate         # Windows
pip install -r requirements.txt
cp .env.example .env            # Then add your API credentials if you have them
```

### Picking up an issue

1. Go to the [Issues tab](https://github.com/rabahbabaci/ListIQ/issues) on GitHub
2. Browse open issues — they're labeled `code` or `no-code` so you can find what fits
3. Comment **"I'll take this"** on the one you want so nobody duplicates work
4. Each issue includes: a description, acceptance criteria, file paths, and a branch name

### Working on it

```bash
git checkout main
git pull
git checkout -b feature/issue-name   # Use the branch name from the issue
```

Do your work — use whatever tools you like (ChatGPT, Copilot, VS Code, etc). Just follow the file paths and acceptance criteria listed in the issue.

### Submitting your work

```bash
git add .
git commit -m "short description of what you did"
git push origin feature/issue-name
```

Then go to GitHub and open a **Pull Request**:
- Add a short description of what you did
- Reference the issue (e.g., `Closes #3`)
- Rabah will review and merge

### Three rules

1. **Never push to `main` directly** — it's protected. Everything goes through a PR.
2. **One issue per branch** — keeps things clean and easy to review.
3. **Ask in the group chat if you're stuck** — no question is too small.
