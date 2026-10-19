"""
finance_engine.py - All of the money math. No AI here, on purpose.

Course: ITAI 2372 - Module 04 (AI in Finance)
Project: NextDollar Compass

WHY THE MATH IS NOT DONE BY THE AI
----------------------------------
Large language models are good at explaining things but can make arithmetic
mistakes. In finance a wrong number can cost someone real money, so every
number in the plan (interest, payoff months, budget totals) is calculated
here with ordinary, testable Python. Gemini only *explains* these numbers
afterwards, and it is told to use only the numbers this file produced.

WHAT IT CALCULATES
------------------
  * monthly take-home pay from paychecks of any frequency
  * spending by category, and needs / wants / savings (the 50/30/20 rule)
  * each debt: monthly interest, payoff time, credit-card utilization
  * debt-to-income ratio and emergency-fund coverage
  * a month-by-month PLAN that splits free cash across the user's goals in
    priority order, rolls money forward when a goal is finished, and lets
    paid-off loan payments "snowball" into the next goal
  * avalanche vs. snowball vs. minimum-payment comparisons
  * how much faster a car loan or mortgage ends with extra payments
"""

from __future__ import annotations

import math
from datetime import date

import investments
from categories import TYPE_LABELS

PERIODS_PER_YEAR = {"weekly": 52, "biweekly": 26, "semimonthly": 24, "monthly": 12, "quarterly": 4, "yearly": 1}
MAX_MONTHS = 360  # 30 years

DEBT_KINDS = {
    "credit_card": "Credit card",
    "car": "Car loan",
    "mortgage": "Mortgage",
    "student": "Student loan",
    "personal": "Personal loan",
    "other": "Other loan",
}
# Which debts each payoff goal targets.
GOAL_DEBT_KINDS = {
    "pay_off_cards": {"credit_card", "student", "personal", "other"},
    "pay_off_car": {"car"},
    "pay_off_mortgage": {"mortgage"},
}
GOAL_LABELS = {
    "emergency_fund": "Emergency fund",
    "pay_off_cards": "Pay off credit cards & loans",
    "pay_off_car": "Pay off car early",
    "pay_off_mortgage": "Pay off mortgage early",
    "save_for_purchase": "Save for a purchase",
    "invest": "Invest for the long term",
}
# Share of free cash by priority rank (1st, 2nd, ...). Re-balanced as goals finish.
PRIORITY_WEIGHTS = {1: [1.0], 2: [0.6, 0.4], 3: [0.5, 0.3, 0.2], 4: [0.4, 0.3, 0.2, 0.1],
                    5: [0.35, 0.25, 0.2, 0.12, 0.08], 6: [0.3, 0.25, 0.18, 0.12, 0.1, 0.05]}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def num(value, default: float = 0.0, lo: float = 0.0, hi: float = 1e9) -> float:
    """Turn user input into a safe number (blank, text or negative -> default/limits)."""
    try:
        x = float(str(value).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return default
    if math.isnan(x) or math.isinf(x):
        return default
    return max(lo, min(hi, x))


def to_monthly(amount: float, frequency: str) -> float:
    return amount * PERIODS_PER_YEAR.get((frequency or "monthly").lower(), 12) / 12


def month_label(months_from_now: int | None, start: date | None = None) -> str | None:
    if months_from_now is None or months_from_now <= 0:
        return None
    start = start or date.today()
    total = start.year * 12 + (start.month - 1) + months_from_now
    return date(total // 12, total % 12 + 1, 1).strftime("%b %Y")


def annuity_payment(balance: float, apr: float, months: int) -> float:
    """Fixed monthly payment that pays off `balance` in `months` at `apr` %."""
    if months <= 0:
        return balance
    r = apr / 1200
    if r == 0:
        return balance / months
    return balance * r / (1 - (1 + r) ** -months)


def payoff_schedule(balance: float, apr: float, payment: float, extra: float = 0.0,
                    max_months: int = 600) -> dict:
    """Months and total interest to pay off one loan with a fixed payment."""
    if balance <= 0:
        return {"months": 0, "interest": 0.0, "never": False}
    r = apr / 1200
    pay = payment + extra
    if pay <= balance * r + 0.01:
        return {"months": None, "interest": None, "never": True}
    bal, months, interest = balance, 0, 0.0
    while bal > 0.005 and months < max_months:
        i = bal * r
        interest += i
        bal = bal + i - min(pay, bal + i)
        months += 1
    return {"months": months, "interest": round(interest, 2), "never": bal > 0.005}


def card_minimum(balance: float, apr: float) -> float:
    """Typical card minimum when the user does not know it: 1% + interest, at least $25."""
    if balance <= 0:
        return 0.0
    return round(min(balance, max(25.0, balance * 0.01 + balance * apr / 1200)), 2)


# ---------------------------------------------------------------------------
# Income, spending, debts
# ---------------------------------------------------------------------------
def summarize_income(income: dict) -> dict:
    sources, net, gross, gross_known = [], 0.0, 0.0, True
    for p in income.get("paychecks", []) or []:
        freq = p.get("frequency", "biweekly")
        n = to_monthly(num(p.get("net")), freq)
        g = to_monthly(num(p.get("gross")), freq)
        if n <= 0:
            continue
        if g <= 0:
            gross_known = False
        net += n
        gross += g if g > 0 else n
        sources.append({"label": p.get("label") or "Paycheck", "monthly": round(n, 2), "frequency": freq,
                        "kind": "paycheck"})
    for o in income.get("other", []) or []:
        m = to_monthly(num(o.get("amount")), o.get("frequency", "monthly"))
        if m <= 0:
            continue
        net += m
        gross += m
        sources.append({"label": o.get("label") or "Other income", "monthly": round(m, 2),
                        "frequency": o.get("frequency", "monthly"), "kind": "other"})
    return {"monthly_net": round(net, 2), "monthly_gross": round(gross, 2), "gross_known": gross_known and net > 0,
            "sources": sources}


def summarize_spending(expenses: list[dict], has_debts: bool, cut_pct: float) -> dict:
    """Totals by category/type. Savings transfers count as free cash for goals."""
    by_cat: dict[str, dict] = {}
    by_type = {t: 0.0 for t in TYPE_LABELS}
    moved_to_debts, moved_to_savings = [], 0.0
    items = []
    for e in expenses or []:
        monthly = num(e.get("monthly_amount"), default=-1)
        if monthly < 0:
            monthly = to_monthly(num(e.get("amount")), e.get("frequency", "monthly"))
        if monthly <= 0:
            continue
        etype = e.get("type") or "want"
        cat = e.get("category") or "Uncategorized"
        sub = e.get("subcategory") or "Uncategorized"
        if etype == "debt" and has_debts:
            moved_to_debts.append(e.get("description", sub))
            continue
        if etype == "savings":
            moved_to_savings += monthly
            continue
        if etype == "want" and cut_pct > 0:
            monthly *= (1 - cut_pct / 100)
        by_type[etype] = by_type.get(etype, 0.0) + monthly
        c = by_cat.setdefault(cat, {"category": cat, "amount": 0.0, "subs": {}})
        c["amount"] += monthly
        s = c["subs"].setdefault(sub, {"name": sub, "amount": 0.0, "type": etype})
        s["amount"] += monthly
        items.append({"description": e.get("description"), "subcategory": sub, "type": etype, "monthly": monthly})

    total = sum(by_type.values())
    cats = []
    for c in sorted(by_cat.values(), key=lambda c: -c["amount"]):
        subs = sorted(c["subs"].values(), key=lambda s: -s["amount"])
        cats.append({"category": c["category"], "amount": round(c["amount"], 2),
                     "pct": round(100 * c["amount"] / total, 1) if total else 0,
                     "subcategories": [{**s, "amount": round(s["amount"], 2)} for s in subs]})
    wants = sorted([s for c in by_cat.values() for s in c["subs"].values() if s["type"] == "want"],
                   key=lambda s: -s["amount"])
    return {"monthly_total": round(total, 2), "by_category": cats,
            "by_type": {k: round(v, 2) for k, v in by_type.items()},
            "moved_to_debts": moved_to_debts, "savings_transfers": round(moved_to_savings, 2),
            "top_wants": [{"name": s["name"], "amount": round(s["amount"], 2)} for s in wants[:3]],
            "item_count": len(items)}


def normalize_debts(debts: list[dict]) -> tuple[list[dict], list[str]]:
    """Clean up debt inputs and fill in missing minimum payments."""
    out, warnings = [], []
    for i, d in enumerate(debts or []):
        kind = d.get("kind") if d.get("kind") in DEBT_KINDS else "other"
        bal = num(d.get("balance"))
        if bal <= 0:
            continue
        apr = num(d.get("apr"), hi=100)
        escrow = num(d.get("escrow")) if kind == "mortgage" else 0.0
        pay = num(d.get("min_payment"))
        remaining = int(num(d.get("remaining_months"), hi=600))
        name = (d.get("name") or DEBT_KINDS[kind]).strip()
        estimated = False
        if pay <= 0:
            estimated = True
            if kind == "credit_card":
                pay = card_minimum(bal, apr)
            elif remaining > 0:
                pay = annuity_payment(bal, apr, remaining) + escrow
            else:
                pay = annuity_payment(bal, apr, 360 if kind == "mortgage" else 60) + escrow
        pi_payment = max(0.0, pay - escrow)
        monthly_interest = bal * apr / 1200
        if pi_payment <= monthly_interest + 0.01:
            warnings.append(f"{name}: the payment (${pi_payment:,.0f}) does not cover the monthly interest "
                            f"(${monthly_interest:,.0f}), so the balance will never go down at this rate.")
        limit = num(d.get("credit_limit")) if kind == "credit_card" else 0.0
        out.append({
            "id": d.get("id") or f"debt{i}", "name": name, "kind": kind, "kind_label": DEBT_KINDS[kind],
            "balance": round(bal, 2), "apr": round(apr, 3), "payment": round(pay, 2),
            "pi_payment": round(pi_payment, 2), "escrow": round(escrow, 2), "estimated_payment": estimated,
            "monthly_interest": round(monthly_interest, 2), "credit_limit": round(limit, 2),
            "utilization": round(100 * bal / limit, 1) if limit > 0 else None,
            "annual_fee": num(d.get("annual_fee")), "penalty_apr": num(d.get("penalty_apr"), hi=100),
        })
    return out, warnings


# ---------------------------------------------------------------------------
# The month-by-month plan
# ---------------------------------------------------------------------------
def _order(debts: list[dict], method: str) -> list[dict]:
    if method == "snowball":
        return sorted(debts, key=lambda d: (d["bal"], -d["apr"]))
    return sorted(debts, key=lambda d: (-d["apr"], d["bal"]))  # avalanche


def simulate(debts: list[dict], goals: list[dict], base_free: float, start_savings: float,
             invest_rate: float, method: str, horizon_months: int, record: bool = True) -> dict:
    """
    Walk forward one month at a time:
      1. every debt grows by its interest, then gets its regular payment
      2. free cash (+ payments freed by finished loans, + leftovers) is split
         across unfinished goals by priority weight
      3. a goal that finishes passes its share to the remaining goals
    """
    ds = [{**d, "bal": d["balance"], "paid_month": None} for d in debts]
    gs = []
    weights = PRIORITY_WEIGHTS.get(len(goals), [1 / max(1, len(goals))] * len(goals))
    for g, w in zip(goals, weights):
        st = {**g, "w": w, "done_month": None, "bal": 0.0, "first_alloc": 0.0}
        if g["type"] == "emergency_fund":
            st["bal"] = min(start_savings, g["target"])
            if st["bal"] >= g["target"]:
                st["done_month"] = 0
        elif g["type"] == "save_for_purchase":
            st["bal"] = min(g.get("saved", 0.0), g["target"])
            if g["target"] <= 0 or st["bal"] >= g["target"]:
                st["done_month"] = 0
        elif g["type"] in GOAL_DEBT_KINDS:
            if not any(d["kind"] in GOAL_DEBT_KINDS[g["type"]] for d in ds):
                st["done_month"] = 0
        gs.append(st)

    freed, carry, invest_bal, unassigned, interest_paid, contributed = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
    hist = {"debt": [], "saved": [], "invest": [], "contributed": []}
    milestones = []
    r_inv = invest_rate / 12

    def debt_paid(d, m):
        d["paid_month"] = m
        milestones.append({"month": m, "label": f"{d['name']} paid off", "kind": "debt"})

    def finite_done():
        return all(g["done_month"] is not None for g in gs if g["type"] != "invest")

    m = 0
    while m < MAX_MONTHS:
        m += 1
        newly_freed = 0.0
        # 1) interest and regular payments
        for d in ds:
            if d["bal"] <= 0:
                continue
            i = d["bal"] * d["apr"] / 1200
            interest_paid += i
            d["bal"] += i
            pay = min(d["pi_payment"], d["bal"])
            d["bal"] -= pay
            if d["bal"] <= 0.005:
                d["bal"] = 0.0
                debt_paid(d, m)
                carry += d["pi_payment"] - pay      # unused part of this month's payment
                newly_freed += d["pi_payment"]      # whole payment is free from next month
        invest_bal *= (1 + r_inv)

        # 2) split free cash across goals
        pool = base_free + freed + carry
        carry = 0.0
        active = [g for g in gs if g["done_month"] is None]
        if pool > 0 and active:
            wsum = sum(g["w"] for g in active)
            for g in active:
                amt = pool * g["w"] / wsum
                if m == 1:
                    g["first_alloc"] = amt
                left = 0.0
                if g["type"] in ("emergency_fund", "save_for_purchase"):
                    g["bal"] += amt
                    if g["bal"] >= g["target"]:
                        left = g["bal"] - g["target"]
                        g["bal"] = g["target"]
                        g["done_month"] = m
                elif g["type"] == "invest":
                    invest_bal += amt
                    contributed += amt
                else:
                    targets = _order([d for d in ds if d["kind"] in GOAL_DEBT_KINDS[g["type"]] and d["bal"] > 0],
                                     method)
                    left = amt
                    for d in targets:
                        p = min(left, d["bal"])
                        d["bal"] -= p
                        left -= p
                        if d["bal"] <= 0.005:
                            d["bal"] = 0.0
                            debt_paid(d, m)
                            newly_freed += d["pi_payment"]
                        if left <= 0:
                            break
                carry += left
        elif pool > 0:
            unassigned += pool

        # payoff goals finish when their debts reach zero (also via regular payments)
        for g in gs:
            if g["done_month"] is None and g["type"] in GOAL_DEBT_KINDS:
                if all(d["bal"] <= 0 for d in ds if d["kind"] in GOAL_DEBT_KINDS[g["type"]]):
                    g["done_month"] = m
        for g in gs:
            if g["done_month"] == m:
                milestones.append({"month": m, "label": f"{g['label']} - done", "kind": "goal"})
        freed += newly_freed

        if record:
            hist["debt"].append(round(sum(d["bal"] for d in ds), 2))
            hist["saved"].append(round(sum(g["bal"] for g in gs if g["type"] in ("emergency_fund",
                                                                                   "save_for_purchase"))
                                       + unassigned, 2))
            hist["invest"].append(round(invest_bal, 2))
            hist["contributed"].append(round(contributed, 2))
        if m >= horizon_months and finite_done() and all(d["bal"] <= 0 for d in ds):
            break

    debt_free = max((d["paid_month"] for d in ds), default=0) if all(d["paid_month"] for d in ds) else None
    small = [d for d in ds if d["kind"] != "mortgage"]
    non_mortgage_free = (max((d["paid_month"] for d in small), default=0)
                         if all(d["paid_month"] for d in small) else None)
    return {
        "non_mortgage_free_month": non_mortgage_free if small else 0,
        "months_simulated": m, "history": hist, "milestones": sorted(milestones, key=lambda x: x["month"]),
        "debt_free_month": debt_free if ds else 0, "interest_paid": round(interest_paid, 2),
        "invest_balance": round(invest_bal, 2), "invest_contributed": round(contributed, 2),
        "goals": gs, "debts": ds, "unassigned": round(unassigned, 2),
    }


def value_at_month(series: list[float], month: int) -> float | None:
    if not series:
        return None
    return series[min(len(series), max(1, month)) - 1]


# ---------------------------------------------------------------------------
# Build the full plan
# ---------------------------------------------------------------------------
def build_plan(profile: dict) -> dict:
    cut = num(profile.get("spending_cut_pct"), hi=90)
    method = "snowball" if profile.get("debt_method") == "snowball" else "avalanche"
    income = summarize_income(profile.get("income", {}))
    debts, warnings = normalize_debts(profile.get("debts", []))
    spending = summarize_spending(profile.get("expenses", []), has_debts=bool(debts), cut_pct=cut)
    savings_now = num(profile.get("current_savings"))
    inv_prefs = profile.get("investing", {}) or {}
    horizon_years = num(inv_prefs.get("horizon_years"), default=10, lo=1, hi=40)

    debt_payments = sum(d["payment"] for d in debts)
    escrow_total = sum(d["escrow"] for d in debts)
    net = income["monthly_net"]
    # Savings transfers are left out of spending, so they are already inside
    # `free` - money the user already sets aside is available for goals.
    free = net - spending["monthly_total"] - debt_payments
    free_for_goals = free

    needs = spending["by_type"].get("need", 0) + debt_payments
    wants = spending["by_type"].get("want", 0) + spending["by_type"].get("other", 0)
    giving = spending["by_type"].get("giving", 0)
    essentials = spending["by_type"].get("need", 0) + debt_payments

    # ---- goals in priority order
    raw_goals = [g for g in profile.get("goals", []) if g.get("type") in GOAL_LABELS]
    goals = []
    for g in raw_goals:
        gtype = g["type"]
        goal = {"type": gtype, "label": g.get("label") or GOAL_LABELS[gtype],
                "target_months": int(num(g.get("target_months"), hi=600)) or None}
        if gtype == "emergency_fund":
            months = num(g.get("months_of_expenses"), default=3, lo=1, hi=12)
            goal["months_of_expenses"] = months
            goal["target"] = round(essentials * months, 2)
        elif gtype == "save_for_purchase":
            goal["target"] = num(g.get("target_amount"))
            goal["saved"] = num(g.get("saved"))
            if g.get("label"):
                goal["label"] = f"Save for {g['label']}" if not g["label"].lower().startswith("save") else g["label"]
        goals.append(goal)

    invest_rate = investments.ILLUSTRATIVE_RETURN.get(inv_prefs.get("risk", "moderate"), 0.06)
    if horizon_years < 3:
        invest_rate = 0.025
    horizon_months = int(horizon_years * 12)

    plan_sim = simulate(debts, goals, max(0.0, free_for_goals), savings_now, invest_rate, method, horizon_months)
    base_sim = simulate(debts, [], 0.0, savings_now, 0.0, method, 1, record=True)

    # ---- per-goal results
    goal_results = []
    for g in plan_sim["goals"]:
        res = {"type": g["type"], "label": g["label"], "weight": round(g["w"], 3),
               "first_month_amount": round(g["first_alloc"], 2), "done_month": g["done_month"],
               "done_label": month_label(g["done_month"]) if g["done_month"] else
               ("Already done" if g["done_month"] == 0 else None)}
        if g["type"] in ("emergency_fund", "save_for_purchase"):
            res["target"] = g["target"]
            res["progress"] = round(g["bal"], 2)
        if g["type"] == "emergency_fund":
            res["months_of_expenses"] = g.get("months_of_expenses")
        if g["type"] == "save_for_purchase" and g.get("target_months"):
            need = max(0.0, g["target"] - g.get("saved", 0.0)) / g["target_months"]
            res["needed_per_month_for_target"] = round(need, 2)
            res["on_track"] = g["done_month"] is not None and g["done_month"] <= g["target_months"]
        if g["type"] in ("pay_off_car", "pay_off_mortgage"):
            kinds = GOAL_DEBT_KINDS[g["type"]]
            boosts = []
            for d in debts:
                if d["kind"] not in kinds:
                    continue
                base = payoff_schedule(d["balance"], d["apr"], d["pi_payment"])
                fast = payoff_schedule(d["balance"], d["apr"], d["pi_payment"], extra=g["first_alloc"])
                boost = {"name": d["name"], "extra": round(g["first_alloc"], 2), "baseline": base, "with_extra": fast}
                if base["months"] and fast["months"]:
                    boost["months_saved"] = base["months"] - fast["months"]
                    boost["interest_saved"] = round(base["interest"] - fast["interest"], 2)
                if g.get("target_months"):
                    needed = annuity_payment(d["balance"], d["apr"], g["target_months"]) - d["pi_payment"]
                    boost["target_months"] = g["target_months"]
                    boost["extra_needed_for_target"] = round(max(0.0, needed), 2)
                boosts.append(boost)
            res["loans"] = boosts
        if g["type"] == "invest":
            res["value_at_horizon"] = value_at_month(plan_sim["history"]["invest"], horizon_months)
        goal_results.append(res)

    # ---- avalanche vs snowball vs minimums for cards & small loans
    strategies = None
    small = [d for d in debts if d["kind"] in GOAL_DEBT_KINDS["pay_off_cards"]]
    if small:
        extra = next((g["first_month_amount"] for g in goal_results if g["type"] == "pay_off_cards"), 0.0)
        strategies = {"extra_per_month": round(extra, 2)}
        for name in ("avalanche", "snowball"):
            sim = simulate(small, [{"type": "pay_off_cards", "label": "cards", "target_months": None}],
                           extra, 0.0, 0.0, name, 1, record=False)
            strategies[name] = {"months": sim["debt_free_month"], "interest": sim["interest_paid"],
                                "order": [m["label"].replace(" paid off", "") for m in sim["milestones"]
                                          if m["kind"] == "debt"]}
        mins = simulate(small, [], 0.0, 0.0, 0.0, method, 1, record=False)
        strategies["minimums_only"] = {"months": mins["debt_free_month"], "interest": mins["interest_paid"]}

    # ---- emergency fund and ratios
    gross = income["monthly_gross"]
    dti = round(100 * debt_payments / gross, 1) if gross > 0 else None
    card_bal = sum(d["balance"] for d in debts if d["kind"] == "credit_card" and d["credit_limit"] > 0)
    card_lim = sum(d["credit_limit"] for d in debts if d["kind"] == "credit_card" and d["credit_limit"] > 0)
    utilization = round(100 * card_bal / card_lim, 1) if card_lim > 0 else None
    months_covered = round(savings_now / essentials, 1) if essentials > 0 else None

    # ---- warnings & suggestions (plain-language guardrails)
    goal_order = [g["type"] for g in goals]
    high_apr = [d for d in debts if d["kind"] == "credit_card" and d["apr"] >= 10]
    if net <= 0:
        warnings.append("Add your income first - the plan needs at least one paycheck.")
    elif free < 0:
        warnings.append(f"You are spending ${-free:,.0f} more than you bring home each month. "
                        "The plan focuses on closing that gap before any goal.")
    if "invest" in goal_order and high_apr:
        inv_i = goal_order.index("invest")
        card_i = goal_order.index("pay_off_cards") if "pay_off_cards" in goal_order else 99
        if inv_i < card_i:
            top = max(high_apr, key=lambda d: d["apr"])
            warnings.append(f"Investing is ranked above your credit cards. {top['name']} charges {top['apr']:.1f}% "
                            "a year - paying it off is a guaranteed 'return' of that rate, which is higher than "
                            "long-term stock market averages.")
    if "invest" in goal_order and (months_covered or 0) < 1 and "emergency_fund" not in goal_order:
        warnings.append("You have less than one month of essential costs saved. Many planners suggest a small "
                        "emergency fund before investing, so a surprise bill does not go on a credit card.")
    if utilization is not None and utilization > 30:
        warnings.append(f"Credit-card utilization is {utilization:.0f}%. Keeping it under 30% generally helps "
                        "credit scores.")
    if dti is not None and dti > 43:
        warnings.append(f"Debt payments take {dti:.0f}% of gross income. Lenders often see above 43% as high risk.")
    elif dti is not None and dti > 36:
        warnings.append(f"Debt payments take {dti:.0f}% of gross income - above the 36% many lenders prefer.")
    if inv_prefs.get("screen") == "shariah" and any(d["apr"] > 0 for d in debts):
        warnings.append("Note for Islamic finance: some of your debts charge interest. Many people who follow "
                        "Shariah guidelines move interest-bearing debt higher in their goal order.")

    suggestions = []
    if spending["top_wants"]:
        for w in spending["top_wants"]:
            suggestions.append({"name": w["name"], "amount": w["amount"], "save_if_cut_20": round(w["amount"] * 0.2, 2)})

    invest_goal = next((g for g in goal_results if g["type"] == "invest"), None)
    invest_monthly = invest_goal["first_month_amount"] if invest_goal else 0.0
    investing = investments.build_investing(inv_prefs, invest_monthly, horizon_years)
    if invest_goal:
        investing["projection"] = {
            "years": horizon_years, "value": invest_goal.get("value_at_horizon"),
            "contributed": value_at_month(plan_sim["history"]["contributed"], horizon_months),
        }

    return {
        "generated": date.today().isoformat(),
        "income": income,
        "spending": spending,
        "debts": {"items": debts, "total_balance": round(sum(d["balance"] for d in debts), 2),
                  "monthly_payments": round(debt_payments, 2), "escrow_in_payments": round(escrow_total, 2),
                  "monthly_interest": round(sum(d["monthly_interest"] for d in debts), 2),
                  "dti": dti, "dti_basis": "gross" if income["gross_known"] else "take-home",
                  "card_utilization": utilization},
        "cash_flow": {"net_income": net, "spending": spending["monthly_total"], "debt_payments": round(debt_payments, 2),
                      "free_cash": round(free, 2), "free_for_goals": round(max(0.0, free_for_goals), 2),
                      "savings_transfers": spending["savings_transfers"], "spending_cut_pct": cut},
        "budget_rule": {
            "needs": round(needs, 2), "wants": round(wants, 2), "giving": round(giving, 2),
            "savings": round(max(0.0, net - needs - wants - giving), 2),
            "needs_pct": round(100 * needs / net, 1) if net else 0,
            "wants_pct": round(100 * (wants + giving) / net, 1) if net else 0,
            "savings_pct": round(100 * max(0.0, net - needs - wants - giving) / net, 1) if net else 0,
        },
        "emergency": {"essential_monthly": round(essentials, 2), "current_savings": savings_now,
                      "months_covered": months_covered},
        "goals": goal_results,
        "debt_method": method,
        "strategies": strategies,
        "timeline": {
            "months": plan_sim["months_simulated"], "history": plan_sim["history"],
            "milestones": [{**m, "date": month_label(m["month"])} for m in plan_sim["milestones"]],
            "debt_free_month": plan_sim["debt_free_month"], "debt_free_date": month_label(plan_sim["debt_free_month"]),
            "interest_with_plan": plan_sim["interest_paid"],
            "baseline_debt_free_month": base_sim["debt_free_month"],
            "baseline_debt_free_date": month_label(base_sim["debt_free_month"]),
            "interest_minimums_only": base_sim["interest_paid"],
            "has_mortgage": any(d["kind"] == "mortgage" for d in debts),
            "non_mortgage_free_month": plan_sim["non_mortgage_free_month"],
            "non_mortgage_free_date": month_label(plan_sim["non_mortgage_free_month"]),
            "baseline_non_mortgage_free_month": base_sim["non_mortgage_free_month"],
            "baseline_non_mortgage_free_date": month_label(base_sim["non_mortgage_free_month"]),
            "interest_saved": round(base_sim["interest_paid"] - plan_sim["interest_paid"], 2)
            if base_sim["debt_free_month"] is not None and plan_sim["debt_free_month"] is not None else None,
        },
        "investing": investing,
        "warnings": warnings,
        "suggestions": suggestions,
    }
