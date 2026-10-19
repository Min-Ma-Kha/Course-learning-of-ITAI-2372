"""
investments.py - Educational investing options, filtered by the user's
values and risk comfort.

Course: ITAI 2372 - Module 04 (AI in Finance)
Project: NextDollar Compass

IMPORTANT: THIS IS EDUCATION, NOT ADVICE
----------------------------------------
The app does not tell anyone what to buy. It shows:
  * an example "mix" (how much in stocks, bonds, cash...) that is commonly
    used for a given risk level, and
  * a short list of well-known funds that fit each part of that mix and the
    user's values, so they can research them and CHOOSE for themselves.

Fund facts were checked in October 2026 (fund names, what each fund screens
out). Funds change, close, and update their rules - always read the fund's
own fact sheet before investing. Expense ratios are left out on purpose
because they change.

VALUES SCREENS
--------------
  shariah     - Islamic (Shariah) guidelines: avoids interest-based finance,
                alcohol, gambling, pork and similar industries, plus debt-ratio
                screens. Funds below follow AAOIFI-style or FTSE/Dow Jones
                Islamic index screening with a Shariah board.
  catholic    - follows the U.S. Conference of Catholic Bishops (USCCB)
                Socially Responsible Investment Guidelines.
  biblical    - "biblically responsible investing" (BRI) standards.
  fossil_free - excludes companies that own fossil fuel reserves.
"""

from __future__ import annotations

SCREENS = {
    "none": "No restrictions",
    "shariah": "Islamic (Shariah-compliant)",
    "catholic": "Catholic values (USCCB guidelines)",
    "biblical": "Biblically responsible (Christian)",
    "fossil_free": "Fossil-fuel free",
}

SLEEVES = {
    "us_stocks": "U.S. stocks",
    "intl_stocks": "International stocks",
    "bonds": "Bonds / income",
    "real_estate": "Real estate",
    "cash": "Cash & savings",
    "crypto": "Crypto",
}

# Each option: which part of the mix it fills, which screens it fits, a risk
# level from 1 (calm) to 5 (very bumpy), and a one-line plain explanation.
CATALOG: list[dict] = [
    # --- broad, unscreened index funds -------------------------------------------------
    {"ticker": "VTI", "name": "Vanguard Total Stock Market ETF", "sleeve": "us_stocks", "kind": "ETF", "risk": 4,
     "screens": ["none"], "about": "Owns almost every U.S. public company in one fund."},
    {"ticker": "VOO", "name": "Vanguard S&P 500 ETF", "sleeve": "us_stocks", "kind": "ETF", "risk": 4,
     "screens": ["none"], "about": "Tracks the 500 largest U.S. companies."},
    {"ticker": "VXUS", "name": "Vanguard Total International Stock ETF", "sleeve": "intl_stocks", "kind": "ETF",
     "risk": 4, "screens": ["none"], "about": "Companies outside the U.S., developed and emerging markets."},
    {"ticker": "BND", "name": "Vanguard Total Bond Market ETF", "sleeve": "bonds", "kind": "ETF", "risk": 2,
     "screens": ["none", "catholic", "biblical", "fossil_free"],
     "about": "U.S. government and company bonds; steadier than stocks. (Not screened for values.)"},
    {"ticker": "VNQ", "name": "Vanguard Real Estate ETF", "sleeve": "real_estate", "kind": "ETF", "risk": 4,
     "screens": ["none"], "about": "Real estate investment trusts (REITs) - landlords of offices, apartments, etc."},
    # --- Shariah-compliant -------------------------------------------------------------
    {"ticker": "SPUS", "name": "SP Funds S&P 500 Sharia Industry Exclusions ETF", "sleeve": "us_stocks",
     "kind": "ETF", "risk": 4, "screens": ["shariah"],
     "about": "S&P 500 companies screened to AAOIFI guidelines (business activity and debt ratios)."},
    {"ticker": "HLAL", "name": "Wahed FTSE USA Shariah ETF", "sleeve": "us_stocks", "kind": "ETF", "risk": 4,
     "screens": ["shariah"], "about": "Large and mid-size U.S. companies from the FTSE Shariah USA index."},
    {"ticker": "UMMA", "name": "Wahed Dow Jones Islamic World ETF", "sleeve": "intl_stocks", "kind": "ETF",
     "risk": 4, "screens": ["shariah"], "about": "Shariah-screened large companies outside the U.S."},
    {"ticker": "SPSK", "name": "SP Funds Dow Jones Global Sukuk ETF", "sleeve": "bonds", "kind": "ETF", "risk": 2,
     "screens": ["shariah"], "about": "Sukuk - Islamic certificates used in place of interest-paying bonds."},
    {"ticker": "SPRE", "name": "SP Funds S&P Global REIT Sharia ETF", "sleeve": "real_estate", "kind": "ETF",
     "risk": 4, "screens": ["shariah"], "about": "Real estate trusts that pass Shariah screens."},
    # --- Faith-based (Christian) ------------------------------------------------------
    {"ticker": "CATH", "name": "Global X S&P 500 Catholic Values ETF", "sleeve": "us_stocks", "kind": "ETF",
     "risk": 4, "screens": ["catholic"],
     "about": "S&P 500 minus companies at odds with USCCB guidelines."},
    {"ticker": "BIBL", "name": "Inspire 100 ETF", "sleeve": "us_stocks", "kind": "ETF", "risk": 4,
     "screens": ["biblical"], "about": "100 large U.S. companies chosen with biblically responsible screens."},
    # --- Environmental ----------------------------------------------------------------
    {"ticker": "SPYX", "name": "SPDR S&P 500 Fossil Fuel Reserves Free ETF", "sleeve": "us_stocks", "kind": "ETF",
     "risk": 4, "screens": ["fossil_free"], "about": "S&P 500 without companies that own oil, gas or coal reserves."},
    # --- Cash --------------------------------------------------------------------------
    {"ticker": "HYSA", "name": "High-yield savings or money market account", "sleeve": "cash", "kind": "Account",
     "risk": 1, "screens": ["none", "catholic", "biblical", "fossil_free"],
     "about": "FDIC/NCUA-insured savings at a bank or credit union; earns interest."},
    {"ticker": "NIA", "name": "Non-interest checking/savings account", "sleeve": "cash", "kind": "Account", "risk": 1,
     "screens": ["shariah"], "about": "Keeps cash safe without earning interest (riba)."},
    # --- Crypto (very high risk) ------------------------------------------------------
    {"ticker": "IBIT", "name": "iShares Bitcoin Trust ETF", "sleeve": "crypto", "kind": "Crypto ETF", "risk": 5,
     "screens": ["none", "catholic", "biblical", "fossil_free"],
     "about": "Holds bitcoin; buy it like a stock in a regular brokerage account."},
    {"ticker": "ETHA", "name": "iShares Ethereum Trust ETF", "sleeve": "crypto", "kind": "Crypto ETF", "risk": 5,
     "screens": ["none", "catholic", "biblical", "fossil_free"], "about": "Holds ether (Ethereum)."},
    {"ticker": "BTC", "name": "Bitcoin (direct, on an exchange)", "sleeve": "crypto", "kind": "Crypto", "risk": 5,
     "screens": ["none", "shariah", "catholic", "biblical", "fossil_free"],
     "about": "Owning the coin itself; you must keep your account and keys secure."},
]

# Example mixes (percent of invested money). Common teaching examples, not rules.
MIXES = {
    "conservative": {"us_stocks": 25, "intl_stocks": 10, "bonds": 50, "real_estate": 5, "cash": 10, "crypto": 0},
    "moderate": {"us_stocks": 45, "intl_stocks": 15, "bonds": 30, "real_estate": 5, "cash": 5, "crypto": 0},
    "aggressive": {"us_stocks": 60, "intl_stocks": 20, "bonds": 10, "real_estate": 7, "cash": 3, "crypto": 0},
}
CRYPTO_CAP = {"conservative": 0, "moderate": 2, "aggressive": 5}  # % taken from U.S. stocks if crypto is chosen
ILLUSTRATIVE_RETURN = {"conservative": 0.04, "moderate": 0.06, "aggressive": 0.07}  # yearly, for illustration only


def options_for(sleeve: str, screen: str, assets: list[str]) -> list[dict]:
    """Funds that fit a part of the mix and the user's values."""
    picks = [o for o in CATALOG if o["sleeve"] == sleeve and screen in o["screens"]]
    if "crypto" not in assets and sleeve == "crypto":
        return []
    # Someone who only wants crypto ETFs (not coins) still sees both; that is fine.
    return picks


def build_investing(prefs: dict, monthly_amount: float, horizon_years: float) -> dict:
    risk = prefs.get("risk", "moderate")
    if risk not in MIXES:
        risk = "moderate"
    screen = prefs.get("screen", "none")
    if screen not in SCREENS:
        screen = "none"
    assets = prefs.get("assets") or ["etfs"]
    notes: list[str] = []

    mix = dict(MIXES[risk])
    if "crypto" in assets:
        cap = CRYPTO_CAP[risk]
        mix["crypto"] = cap
        mix["us_stocks"] -= cap
        if cap == 0:
            notes.append("Crypto is set to 0% for a conservative risk level because prices can fall more than 50% "
                         "in a short time. Raise your risk level to see a small crypto slice.")
        else:
            notes.append(f"Crypto is capped at {cap}% here. Many educators suggest keeping crypto to a small slice "
                         "you could afford to lose.")

    if horizon_years < 3:
        mix = {"us_stocks": 0, "intl_stocks": 0, "bonds": 30, "real_estate": 0, "cash": 70, "crypto": 0}
        notes.append("Money you need within about 3 years is usually kept out of stocks and crypto, because a "
                     "market drop may not recover in time. The example mix is mostly cash and bonds.")

    if screen == "shariah":
        notes.append("Shariah-compliant funds hold sukuk instead of interest-paying bonds and avoid interest income. "
                     "Scholars differ on cryptocurrency; if you follow Islamic guidelines, ask a qualified scholar "
                     "before buying crypto. Many people also check holdings with a screening service such as "
                     "Zoya or Musaffa.")
    if screen in ("catholic", "biblical", "fossil_free"):
        notes.append("Values-screened bond funds are limited, so the bond option shown is a standard bond fund. "
                     "Check the fund company's site for screened alternatives.")
    if prefs.get("custom_values"):
        notes.append(f"Your note: “{prefs['custom_values']}”. Use a fund's holdings list to check it "
                     "matches - the app cannot verify custom restrictions.")
    if "stocks" in assets:
        notes.append("Individual stocks: one company can drop sharply, so many beginners hold funds as the core and "
                     "keep any single stock to a small share of their portfolio.")

    sleeves = []
    choices = prefs.get("choices") or {}
    for key, pct in mix.items():
        if pct <= 0:
            continue
        opts = options_for(key, screen, assets)
        chosen = choices.get(key) if choices.get(key) in [o["ticker"] for o in opts] else None
        sleeves.append({
            "key": key, "label": SLEEVES[key], "pct": pct,
            "monthly": round(monthly_amount * pct / 100, 2),
            "options": opts, "chosen": chosen,
        })

    rate = ILLUSTRATIVE_RETURN[risk] if horizon_years >= 3 else 0.025
    return {
        "risk": risk, "screen": screen, "screen_label": SCREENS[screen], "assets": assets,
        "horizon_years": horizon_years, "mix": sleeves, "notes": notes,
        "illustrative_return": rate,
        "disclaimer": ("Educational examples only - not a recommendation to buy or sell any security. "
                       "Investing involves risk, including loss of money. Consider talking with a licensed, "
                       "fee-only financial planner before investing."),
    }
