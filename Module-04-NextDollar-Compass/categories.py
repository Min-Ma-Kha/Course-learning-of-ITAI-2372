"""
categories.py - The list of spending categories the app understands.

Course: ITAI 2372 - Module 04 (AI in Finance)
Project: NextDollar Compass

PLAIN-LANGUAGE SUMMARY
----------------------
Every expense gets two labels:
  * a CATEGORY      (big bucket, e.g. "Food")
  * a SUBCATEGORY   (detail, e.g. "Restaurants")

Each subcategory also has a TYPE, which the budget math uses:
  need    - essentials (rent, groceries, electricity, insurance)
  want    - nice-to-haves (restaurants, streaming, hobbies)
  giving  - charity and gifts
  savings - money moved into savings or investments
  debt    - loan or credit-card payments (handled in the Debts step)
  other   - money transfers that could be anything (Zelle, Venmo...)

The machine-learning model (model_training.py) predicts the SUBCATEGORY.
The category and type are then looked up from this table, so the three
labels always stay consistent with each other.
"""

# category -> list of (subcategory, type)
TAXONOMY: dict[str, list[tuple[str, str]]] = {
    "Housing": [
        ("Rent", "need"),
        ("Mortgage Payment", "debt"),
        ("Property Tax & HOA", "need"),
        ("Home Insurance", "need"),
        ("Home Repair & Maintenance", "need"),
    ],
    "Utilities": [
        ("Electricity", "need"),
        ("Water & Trash", "need"),
        ("Natural Gas", "need"),
        ("Internet", "need"),
        ("Mobile Phone", "need"),
    ],
    "Transportation": [
        ("Fuel", "need"),
        ("Car Insurance", "need"),
        ("Car Maintenance & Repair", "need"),
        ("Rideshare & Taxi", "want"),
        ("Public Transit", "need"),
        ("Parking & Tolls", "need"),
    ],
    "Food": [
        ("Groceries", "need"),
        ("Restaurants", "want"),
        ("Fast Food", "want"),
        ("Coffee & Snacks", "want"),
        ("Food Delivery", "want"),
    ],
    "Health": [
        ("Health Insurance", "need"),
        ("Pharmacy", "need"),
        ("Doctor & Dental", "need"),
        ("Gym & Fitness", "want"),
    ],
    "Shopping": [
        ("Clothing", "want"),
        ("Electronics", "want"),
        ("Household Supplies", "need"),
        ("Online Shopping", "want"),
        ("Beauty & Personal Care", "want"),
    ],
    "Entertainment": [
        ("Streaming & Subscriptions", "want"),
        ("Video Games", "want"),
        ("Movies & Events", "want"),
        ("Hobbies & Sports", "want"),
    ],
    "Family & Education": [
        ("Childcare", "need"),
        ("Tuition & Books", "need"),
        ("Pets", "need"),
    ],
    "Giving": [
        ("Charity & Donations", "giving"),
        ("Gifts", "giving"),
    ],
    "Travel": [
        ("Flights", "want"),
        ("Hotels & Lodging", "want"),
    ],
    "Financial": [
        ("Bank Fees", "need"),
        ("Debt Payments", "debt"),
        ("Savings & Investing", "savings"),
        ("Life Insurance", "need"),
        ("Money Transfers", "other"),
    ],
}

# Fallback label when the model is not confident and no AI is available.
UNCATEGORIZED = "Uncategorized"

# Reverse lookups built once at import time.
SUBCATEGORY_TO_CATEGORY: dict[str, str] = {}
SUBCATEGORY_TO_TYPE: dict[str, str] = {}
for _category, _subs in TAXONOMY.items():
    for _sub, _type in _subs:
        SUBCATEGORY_TO_CATEGORY[_sub] = _category
        SUBCATEGORY_TO_TYPE[_sub] = _type

ALL_SUBCATEGORIES: list[str] = list(SUBCATEGORY_TO_CATEGORY)

TYPE_LABELS = {
    "need": "Needs",
    "want": "Wants",
    "giving": "Giving",
    "savings": "Savings",
    "debt": "Debt payments",
    "other": "Transfers",
}


def describe(subcategory: str) -> dict:
    """Return the full label set for one subcategory."""
    if subcategory not in SUBCATEGORY_TO_CATEGORY:
        return {"category": UNCATEGORIZED, "subcategory": UNCATEGORIZED, "type": "want"}
    return {
        "category": SUBCATEGORY_TO_CATEGORY[subcategory],
        "subcategory": subcategory,
        "type": SUBCATEGORY_TO_TYPE[subcategory],
    }


def taxonomy_for_ui() -> list[dict]:
    """The taxonomy in a JSON-friendly shape (used for the override dropdown)."""
    return [
        {"category": cat, "subcategories": [{"name": s, "type": t} for s, t in subs]}
        for cat, subs in TAXONOMY.items()
    ]
