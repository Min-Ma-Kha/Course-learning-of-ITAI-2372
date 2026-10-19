"""
offline_text.py - Plain-language text WITHOUT AI, plus the trimmed plan
summary that is sent to Gemini.

Course: ITAI 2372 - Module 04 (AI in Finance)
Project: NextDollar Compass

When there is no API key (or Gemini is down), the app still explains the
plan using fill-in-the-blank templates and answers common questions with
simple keyword matching. It is less flexible than the LLM, but it is always
correct about the numbers because it reads them straight from the plan.
"""

from __future__ import annotations


def money(x) -> str:
    if x is None:
        return "-"
    return f"${x:,.0f}"


def plan_summary(plan: dict) -> dict:
    """A compact copy of the plan for the LLM (no long chart arrays, no personal names)."""
    inv = plan.get("investing", {})
    return {
        "monthly_take_home": plan["income"]["monthly_net"],
        "monthly_gross": plan["income"]["monthly_gross"],
        "monthly_spending": plan["spending"]["monthly_total"],
        "top_spending_categories": [{"category": c["category"], "monthly": c["amount"]}
                                    for c in plan["spending"]["by_category"][:6]],
        "top_wants": plan["spending"]["top_wants"],
        "budget_rule_50_30_20": plan["budget_rule"],
        "debts": [{"name": d["name"], "type": d["kind_label"], "balance": d["balance"], "apr": d["apr"],
                   "monthly_payment": d["payment"], "monthly_interest": d["monthly_interest"]}
                  for d in plan["debts"]["items"]],
        "debt_to_income_pct": plan["debts"]["dti"],
        "credit_card_utilization_pct": plan["debts"]["card_utilization"],
        "cash_flow": plan["cash_flow"],
        "emergency_fund": plan["emergency"],
        "goals_in_priority_order": [{"goal": g["label"], "first_month_amount": g["first_month_amount"],
                                     "finished": g.get("done_label")} for g in plan["goals"]],
        "debt_method": plan["debt_method"],
        "card_payoff_comparison": plan["strategies"],
        "milestones": plan["timeline"]["milestones"][:10],
        "debt_free_date": plan["timeline"]["debt_free_date"],
        "debt_free_date_minimums_only": plan["timeline"]["baseline_debt_free_date"],
        "interest_saved_vs_minimums": plan["timeline"]["interest_saved"],
        "investing": {
            "risk": inv.get("risk"), "values_screen": inv.get("screen_label"),
            "horizon_years": inv.get("horizon_years"),
            "example_mix": [{"part": s["label"], "pct": s["pct"], "monthly": s["monthly"],
                             "user_choice": s.get("chosen")} for s in inv.get("mix", [])],
            "illustrative_projection": inv.get("projection"),
        } if any(g["type"] == "invest" for g in plan["goals"]) else None,
        "warnings": plan["warnings"],
    }


GOAL_PHRASES = {
    "emergency_fund": "your emergency fund",
    "pay_off_cards": "paying down credit cards and loans",
    "pay_off_car": "paying off the car early",
    "pay_off_mortgage": "paying down the mortgage",
    "save_for_purchase": "your savings goal",
    "invest": "investing",
}


def narrative(plan: dict) -> dict:
    cf = plan["cash_flow"]
    goals = plan["goals"]
    first = [g for g in goals if g["first_month_amount"] > 0]
    if cf["net_income"] <= 0:
        headline = "Add your income to see your plan."
    elif cf["free_cash"] < 0:
        headline = f"You're about {money(-cf['free_cash'])} short each month - let's close that gap first."
    else:
        headline = f"You have about {money(cf['free_for_goals'])} a month to put toward your goals."

    summary = (f"You bring home {money(cf['net_income'])} a month, spend {money(cf['spending'])} on living costs "
               f"and pay {money(cf['debt_payments'])} toward debts. ")
    if first:
        parts = [f"{money(g['first_month_amount'])} to {GOAL_PHRASES.get(g['type'], g['label'].lower())}"
                 for g in first]
        split = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
        summary += f"The plan starts by sending {split}. When a goal is finished, its money moves to the next one."
    elif goals:
        summary += "Right now there is no free cash for goals, so the first step is trimming spending."
    else:
        summary += "Pick a few goals to get a step-by-step plan."

    steps = []
    for g in first[:3]:
        if g["type"] == "emergency_fund":
            steps.append(f"Set an automatic {money(g['first_month_amount'])} monthly transfer into a separate "
                         "savings account for emergencies.")
        elif g["type"] == "pay_off_cards":
            order = (plan.get("strategies") or {}).get(plan["debt_method"], {}).get("order") or []
            target = order[0] if order else "your highest-interest card"
            steps.append(f"Pay the minimums on every card, plus an extra {money(g['first_month_amount'])} "
                         f"on {target}.")
        elif g["type"] in ("pay_off_car", "pay_off_mortgage"):
            loans = g.get("loans") or []
            name = loans[0]["name"] if loans else ("car loan" if g["type"] == "pay_off_car" else "mortgage")
            steps.append(f"Add {money(g['first_month_amount'])} to your {name} payment each month and ask the "
                         "lender to apply it to principal.")
        elif g["type"] == "invest":
            steps.append(f"Research the options in your investing mix before putting in "
                         f"{money(g['first_month_amount'])} a month.")
        elif g["type"] == "save_for_purchase":
            steps.append(f"Move {money(g['first_month_amount'])} a month into a savings bucket for this goal.")
    for s in plan.get("suggestions", [])[:1]:
        steps.append(f"Trimming {s['name'].lower()} by 20% would free up about {money(s['save_if_cut_20'])} a month.")
    if not steps:
        steps.append("List every expense for one month so the app can find room in your budget.")

    return {"headline": headline, "summary": summary, "this_month": steps,
            "watch_outs": plan["warnings"][:3],
            "encouragement": "Small, automatic steps add up - check back each month and adjust."}


def answer(question: str, plan: dict) -> str:
    q = question.lower()
    t = plan["timeline"]
    cf = plan["cash_flow"]
    goals = {g["type"]: g for g in plan["goals"]}
    note = " (Offline answer - add a Gemini API key for full AI answers.)"

    if "debt" in q and ("free" in q or "when" in q):
        if not plan["debts"]["items"]:
            return "You have not listed any debts." + note
        txt = ""
        if t.get("has_mortgage") and t.get("non_mortgage_free_date"):
            txt = (f"Everything except the mortgage is paid off around {t['non_mortgage_free_date']} with this plan, "
                   f"versus {t['baseline_non_mortgage_free_date'] or 'never'} paying only minimums. ")
        txt += (f"Fully debt-free (mortgage included) around {t['debt_free_date'] or 'an unknown date'}"
                + (f"; the plan saves about {money(t['interest_saved'])} in interest overall." if t["interest_saved"]
                   else "."))
        return txt + note
    if "emergency" in q:
        e = plan["emergency"]
        g = goals.get("emergency_fund")
        txt = (f"Your essential costs are about {money(e['essential_monthly'])} a month and your savings cover "
               f"{e['months_covered'] or 0} months. ")
        if g:
            txt += f"The plan builds it to {money(g.get('target'))}, finishing around {g.get('done_label')}."
        return txt + note
    if "card" in q or "avalanche" in q or "snowball" in q:
        s = plan.get("strategies")
        if not s:
            return "You have not listed any credit cards." + note
        return (f"Paying only minimums takes {s['minimums_only']['months'] or 'forever'} months and "
                f"{money(s['minimums_only']['interest'])} in interest. Adding {money(s['extra_per_month'])} a "
                f"month: avalanche (highest rate first) takes {s['avalanche']['months']} months, snowball "
                f"(smallest balance first) takes {s['snowball']['months']} months." + note)
    for key, word in (("pay_off_car", "car"), ("pay_off_mortgage", "mortgage")):
        if word in q and goals.get(key) and goals[key].get("loans"):
            ln = goals[key]["loans"][0]
            return (f"Adding {money(ln['extra'])} a month to {ln['name']} pays it off "
                    f"{ln.get('months_saved', 0)} months sooner and saves about {money(ln.get('interest_saved'))} "
                    "in interest." + note)
    if any(w in q for w in ("invest", "etf", "stock", "crypto", "bitcoin")):
        inv = plan["investing"]
        parts = ", ".join(f"{s['pct']}% {s['label'].lower()}" for s in inv["mix"])
        return (f"Your example {inv['risk']} mix is {parts}. These are educational examples, not advice - "
                "research each fund's fact sheet before buying." + note)
    if any(w in q for w in ("save", "cut", "spend", "budget")):
        tips = "; ".join(f"{s['name']} ({money(s['amount'])}/mo)" for s in plan.get("suggestions", []))
        return (f"Your biggest 'wants' are: {tips or 'none listed'}. Use the 'Find extra money' slider to see how "
                "a small cut speeds up every goal." + note)
    if "afford" in q:
        return (f"After living costs and debt payments you have about {money(cf['free_cash'])} free each month. "
                "A new monthly cost should fit inside that and still leave room for your goals." + note)
    return ("I can answer questions about being debt-free, your emergency fund, credit cards, car or mortgage "
            "payoff, investing options, and where to cut spending." + note)
