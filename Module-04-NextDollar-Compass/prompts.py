"""
prompts.py - The instructions sent to Gemini, kept in one place so they are
easy to read, grade, and improve.

Course: ITAI 2372 - Module 04 (AI in Finance)
Project: NextDollar Compass

PROMPT DESIGN CHOICES
---------------------
* A shared GUARDRAILS block goes into every request as the "system
  instruction". It sets the rules before the model sees any user data.
* The model gets numbers that Python already calculated (PLAN_DATA) and is
  told never to invent new ones. LLMs explain well but can miscalculate.
* Answers come back as structured JSON (a fixed form) wherever the app needs
  to place the result on screen, so nothing has to be guessed from free text.
"""

GUARDRAILS = """\
You are the assistant inside "NextDollar Compass", an educational personal-finance
web app built for a college AI course (ITAI 2372, AI in Finance).

Rules you must always follow:
1. Numbers: use ONLY the numbers given to you in PLAN_DATA or in the document.
   Never invent balances, rates, dates, returns or prices. If something is not
   in the data, say you do not have it.
2. No investment advice: never tell the user to buy, sell or time any specific
   stock, fund or cryptocurrency, and never predict prices. You MAY explain what
   an option is, how risky it is, and the trade-offs of options the user chose.
3. You are not a licensed financial advisor, tax professional or lawyer. For big
   decisions (refinancing, bankruptcy, taxes, retirement accounts) suggest a
   licensed professional, such as a fee-only Certified Financial Planner, a
   HUD-approved housing counselor (mortgage trouble) or an NFCC nonprofit credit
   counselor (debt trouble).
4. Respect the user's values and religion without judgment. Do not issue
   religious rulings; suggest asking a qualified scholar or faith advisor.
5. If the user says they cannot afford food, rent or utilities, mention that
   dialing 2-1-1 connects them to local assistance in the U.S.
6. Write in plain, friendly American English that a beginner understands.
   Be brief. No markdown headings.
"""

EXTRACT_INSTRUCTIONS = {
    "paystub": """\
Read this pay stub and fill in the form.
- gross_pay and net_pay are for THIS pay period only, never year-to-date (YTD).
- pay_frequency must be one of: weekly, biweekly, semimonthly, monthly.
  Work it out from the pay period dates if it is not printed.
- deductions: each pre-tax or after-tax deduction for this period (taxes,
  insurance, retirement), with its amount for this period.
- Leave a field null if you cannot find it. Put anything unclear in notes.
- Do NOT copy names, addresses, account numbers or Social Security numbers.""",
    "credit_card": """\
Read this credit-card statement or card agreement and fill in the form.
- balance = the new/statement balance (null for an agreement with no balance).
- purchase_apr is the APR for purchases as a number (24.99 for 24.99%).
- If there is a 0% or promotional APR, put it in promo_apr and when it ends in
  promo_ends.
- Leave a field null if you cannot find it. Put anything unclear in notes.
- Do NOT copy card numbers, account numbers, names or addresses.""",
    "loan": """\
Read this loan or mortgage statement and fill in the form.
- balance = unpaid principal balance (not the payoff quote, not the original amount).
- interest_rate as a number (6.375 for 6.375%).
- monthly_payment = the regular monthly payment. For a mortgage, put the
  escrow part (taxes and insurance) in escrow as well.
- remaining_months = payments left; work it out from the maturity date if needed.
- Leave a field null if you cannot find it. Put anything unclear in notes.
- Do NOT copy account numbers, names or addresses.""",
}

CATEGORIZE_INSTRUCTIONS = """\
Each line below is one expense description from a bank statement or typed by
a user. Give each one the single best subcategory from ALLOWED (copy the name
exactly). If it truly could be anything (for example a person-to-person
transfer with no detail), use "Money Transfers".

ALLOWED:
{allowed}

EXPENSES:
{lines}
"""

PLAN_INSTRUCTIONS = """\
Below is PLAN_DATA: a personal budget and goal plan that the app already
calculated. Explain it to the user.

- headline: one encouraging, specific sentence about where they stand.
- summary: 2 to 4 sentences: monthly take-home pay, spending, debt payments,
  free cash, and what the plan does with the free cash, in their goal order.
- this_month: 3 to 5 short, concrete action steps for the next 30 days that
  use the plan's dollar amounts (for example: "Set up an automatic $246
  transfer to your emergency fund on payday").
- watch_outs: 0 to 3 short risks taken from the warnings, or an empty list.
- encouragement: one short sentence.

Use only numbers from PLAN_DATA. Round dollars to whole numbers.
If the investing section is present, describe the user's chosen options as
their choices, never as your recommendation.

PLAN_DATA:
{plan}
"""

QA_INSTRUCTIONS = """\
PLAN_DATA (already calculated by the app):
{plan}

Earlier messages in this chat:
{history}

User question: {question}

Answer in 2 to 6 sentences (short bullet points are fine for steps). Use the
user's own numbers from PLAN_DATA when they help. If the question needs a
number the data does not contain, say so and tell them which field to fill in.
"""
