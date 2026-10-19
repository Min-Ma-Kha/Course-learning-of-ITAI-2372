# NextDollar Compass

**ITAI 2372 · Module 04 · AI in Finance** · Houston City College, AAS in Artificial Intelligence
**Author:** Min Ma Kha · **Assignment option:** Option 2 (build your own AI-in-finance application)

*Every next dollar gets a direction.*

> A personal-finance web app that turns a **pay stub, bills and debts** into a **month-by-month plan** for the goals you choose: an emergency fund, paying off credit cards, a car or a mortgage early, saving for something, or investing in a way that fits your values.

> ⚠️ **Student project, for learning only.** Not financial, tax, legal or investment advice. All numbers are estimates. Use the sample documents for demos, never your real statements.

![The finished plan for the sample household](docs/screenshots/05_plan_top.png)

---

## In plain English

**Why the name.** Most people know where *last* month's money went. NextDollar Compass answers where the *next* dollar should go: toward which goal, in what order, and when each goal will be finished.

**The problem.** Most budgeting apps either just track spending or push products. People who live paycheck to paycheck rarely get a clear answer to *"I have $500 left over each month: what should it do first, and when will I be done?"* People who follow religious or ethical guidelines also struggle to find investing information that respects them.

**What the app does,** in five steps:

| Step | You do | The app does |
|---|---|---|
| 1. Income | Upload a pay stub (or type the numbers) | **Gemini reads the stub** and fills in gross pay, take-home pay, pay frequency and deductions |
| 2. Spending | List expenses or upload a bank export (CSV) | A **machine-learning model sorts every expense** into 46 subcategories (needs vs. wants) |
| 3. Debts | Upload card, car-loan or mortgage statements | **Gemini reads the APR, balance, minimum payment, escrow**; the app shows monthly interest |
| 4. Goals & values | Pick goals, put them in order, choose investing comfort and values (Islamic, Catholic, biblically responsible, fossil-free) | Shows how much of your free cash each goal gets |
| 5. Your plan | Read it, adjust it, ask questions | **Python calculates** every number month by month; **Gemini explains** the plan and answers questions |

---

## How it works

```
 Browser (templates/index.html + static/js/app.js)
   │  fetch() JSON / file uploads
   ▼
 Flask app (app.py) ── /api/extract ──► gemini_client.py  (LLM reads PDFs/photos)
   │                                     └► document_reader.py (offline fallback: text patterns)
   ├────────────── /api/categorize ──► categorizer.py  (TF-IDF + Logistic Regression)
   │                                     └► Gemini second opinion when the model is unsure
   ├────────────── /api/plan ───────► finance_engine.py (all the math, no AI)
   │                                     ├► investments.py (educational options + values screens)
   │                                     └► Gemini explains the numbers (or offline_text.py)
   └────────────── /api/ask ────────► Gemini answers using the user's own plan numbers
```

### Three kinds of "AI", each doing what it is best at

1. **Traditional machine learning: the expense categorizer.** TF-IDF features on words *and* character pieces (so `AMZN MKTP US*2K4` and `whataburgr` still work) feed a Logistic Regression model, compared against the Naive Bayes baseline from the Assignment Aid.
2. **Large language model (Google Gemini).** Reads documents into a fixed JSON form (structured output), gives a second opinion on unsure expenses, writes the plan summary, and answers questions.
3. **Plain, testable code for the money math.** LLMs explain well but can make arithmetic mistakes, and in finance a wrong number costs real money. So **Gemini never calculates**. It is given the numbers Python produced and told to use only those.

### The plan simulation

`finance_engine.simulate()` walks forward one month at a time:

1. Every debt grows by its interest, then gets its regular payment.
2. Free cash is split across unfinished goals by priority (1st goal 40%, 2nd 30%, 3rd 20%, 4th 10% when there are four).
3. When a goal finishes, its share moves to the remaining goals, and **a paid-off loan's payment is freed up and rolls into the next goal** (the "snowball" effect across the whole plan).

It also compares **avalanche** (highest interest first), **snowball** (smallest balance first) and **minimum payments only**, and shows how many months and dollars extra payments save on a car loan or mortgage.

### Model results (synthetic data, see `models/evaluation.json`)

Real bank transactions are private, so the model trains on **5,146 synthetic transactions** built from real merchant names written the messy way banks print them (`build_training_data.py`). It is tested two ways:

| Model | Test A: new rows, known merchants | Test B: merchants never seen |
|---|---|---|
| Naive Bayes (Assignment Aid baseline) | 99.0% accuracy | 50.8% accuracy, macro-F1 0.50 |
| **Logistic Regression (used)** | **100%** | **54.2% accuracy, macro-F1 0.56** |

Test A is easy because the merchants were seen in training. **Test B is the honest number:** with an unknown store name, the model can only use clues like "pharmacy" or "insurance". That is why the app uses a **confidence cut-off**: on unseen merchants, guesses at least 40% confident were right **81%** of the time and covered 54% of rows. Less confident guesses go to Gemini, or are marked **Check** for the user to fix in one click. The user always has the final say.

---

## Responsible AI and privacy

| Risk | What the app does |
|---|---|
| AI miscalculates money | All math is plain Python with 26 automated tests; Gemini only explains numbers it is given |
| AI misreads a document | Every extracted number lands in an editable field with a "please check" message |
| AI miscategorizes spending | Confidence cut-off, Gemini second opinion, one-click correction, "Sorted by" badge on every row |
| Acting like an investment adviser | Investing is framed as **education**: example mixes and lists of well-known funds; the user picks. Gemini is instructed never to recommend buying or selling anything, and a disclaimer is shown |
| Risky ordering of goals | Warnings when investing is ranked above high-interest cards, with no emergency fund, or with money needed within 3 years |
| Personal data | Nothing is stored on the server; files are read in memory and dropped. Users are told to black out names and account numbers. Gemini is told not to copy account numbers |
| Third-party AI | When AI mode is on, uploaded documents are sent to Google's Gemini API. Check Google's terms before using real documents (free-tier content may be used to improve Google's products). Demo with the sample files |
| Values and religion | The app filters by recognized screening standards (AAOIFI/Shariah indexes, USCCB guidelines, BRI standards) but never makes religious rulings; it says to ask a qualified scholar or advisor, e.g. on whether crypto is permissible |
| No API key / outage | Every AI feature has an offline fallback, so the app keeps working |

---

## Business use case

**Scenario.** A credit union, an employer's financial-wellness benefit, or a nonprofit financial coach wants members to arrive at a coaching session with a clear picture of their money, instead of spending the first hour sorting receipts.

**Value.**
* Turns a pay stub and a few statements into a budget, debt payoff schedule and goal timeline in minutes.
* Makes interest visible ("$1,264 of your $2,050 mortgage payment this month is interest").
* Serves people mainstream tools overlook: values-screened investing education for Muslim, Catholic and Christian communities, and plain-language help for first-time budgeters.

**Limitations.**
* Estimates only: real card minimums change with the balance, interest rates change, and investment returns are uncertain.
* The categorizer is trained on synthetic data and mostly Texas merchants.
* LLM output can still be wrong or biased; a human coach or the user should review it.

**Path to a real product.** A white-label version for credit unions (member benefit) or employers (wellness benefit), with secure bank connections instead of uploads. A production version would need **GLBA** privacy and safeguarding controls, **investment-adviser registration** before giving personalized investment advice, accessibility testing, and fairness testing across income levels and languages.

---

## Project structure

```
ITAI-2372-Module-04-NextDollar-Compass/
├── app.py                    # Flask routes (the web server)
├── finance_engine.py         # budget, debts, month-by-month plan (no AI)
├── investments.py            # educational fund lists + values screens + example mixes
├── categories.py             # 11 categories / 46 subcategories and their need/want type
├── preprocess.py             # text cleaning for bank descriptions
├── build_training_data.py    # makes the synthetic labeled dataset
├── model_training.py         # trains + compares Naive Bayes vs Logistic Regression
├── categorizer.py            # ML predictions, Gemini second opinion, bank CSV import
├── gemini_client.py          # all Gemini calls, with structured-output schemas
├── prompts.py                # every prompt and the guardrails, in one place
├── document_reader.py        # offline PDF reading (regular expressions)
├── offline_text.py           # plan summary + Q&A without AI
├── make_sample_documents.py  # creates the fake pay stub/statements/CSV
├── templates/index.html      # the page
├── static/css/style.css      # the look
├── static/js/app.js          # the page's behavior (fetch calls, rendering)
├── static/js/charts.js       # hand-made SVG charts (no chart library)
├── data/                     # training data, sample profile, sample documents
├── models/                   # trained model + evaluation.json
├── tests/test_app.py         # 26 automated tests
├── docs/screenshots/         # screenshots for the submission
├── requirements.txt
└── .env.example              # copy to .env and add your Gemini key
```

---

## Run it on your computer (Windows PowerShell)

```powershell
cd ITAI-2372-Module-04-NextDollar-Compass
py --list                      # shows your Python versions (3.12 or newer works)
py -3.12 -m venv .venv          # use a version from that list
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Optional: turn on AI features (otherwise the app runs in offline mode)
$env:GEMINI_API_KEY = "paste-your-key-here"     # or copy .env.example to .env

python app.py
```

Open **http://127.0.0.1:5000** and click **Try a sample household**, or upload the files in `data/sample_documents/`.

| Task | Command |
|---|---|
| Rebuild training data | `python build_training_data.py` |
| Retrain + print scores | `python model_training.py` |
| Run the tests | `python -m unittest -v` |
| Re-create the sample documents | `python make_sample_documents.py` |
| Use another Gemini model | `$env:GEMINI_MODEL = "model-name"` |

**Troubleshooting**
* *`No suitable Python runtime found`*: that Python version is not installed. Run `py --list` and use one of the versions it shows (3.12 or newer).
* *`Activate.ps1 cannot be loaded`*: run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.
* *pip tries to compile scikit-learn or pandas (ARM laptops such as Snapdragon)*: install the **x64 (AMD64)** build of Python 3.12 or newer from python.org. It runs through Windows' built-in emulation, and every package has ready-made wheels.
* *"Gemini rejected the API key"* or *"rate limit"*: check the key, or wait a minute. The app keeps working offline either way.
* *The model file will not load after upgrading scikit-learn*: the app retrains it automatically (about 15 seconds).

---

## How this meets the assignment

| Assignment item | Where |
|---|---|
| Finance-related text data | Pay stubs, statements, card agreements, bank exports (`data/`) |
| Preprocessing & traditional NLP/ML | `preprocess.py`, `model_training.py` (TF-IDF, NB vs LR, two tests, confidence analysis) |
| LLM integration | `gemini_client.py`, `prompts.py`: document reading, categorizing, summaries, Q&A |
| Web interface (Flask + HTML/CSS/JS) | `app.py`, `templates/index.html`, `static/` |
| Business use case & limitations | This README |
| Disclaimers, responsible AI | In-app disclaimers, guardrail prompts, offline fallbacks, tests |
| README with install/run/test steps | This file |

## Sources for fund facts (checked October 2026)

* SP Funds Sharia ETFs (SPUS, SPSK) and AAOIFI screening: [SP Funds launch announcement](https://jotup.co/node/604968), [ETF Strategy](https://etfstrategy.com/sp-funds-debuts-with-sharia-compliant-equity-and-fixed-income-etfs-10339)
* Wahed HLAL and UMMA: [HalalWallet: HLAL](https://www.halalwallet.us/providers/wahed-invest/wahed-ftse-usa-shariah-etf), [HalalWallet: UMMA](https://www.halalwallet.us/providers/wahed-invest/wahed-dow-jones-islamic-world-etf)
* Global X CATH (USCCB guidelines): [Global X fact sheet](https://wp.globalxetfs.com/content/files/CATH-factsheet.pdf)
* Inspire BIBL (biblically responsible investing): [ETF Strategy](https://www.etfstrategy.com/inspire-adds-us-large-cap-etf-to-biblical-values-suite-64258)
* SPDR SPYX (fossil-fuel reserves free): [State Street](https://www.ssga.com/us/en/institutional/etfs/funds/spdr-sp-500-fossil-fuel-reserves-free-etf-spyx)
* iShares IBIT and ETHA: [Motley Fool](https://www.fool.com/coverage/etfs/2026/04/24/ibit-and-etha-charge-the-same-the-similarities-end-there/)
* Gemini document input and structured output: [Google AI for Developers](https://ai.google.dev/gemini-api/docs/document-processing)

Funds change their rules and fees. Always read a fund's current fact sheet.
