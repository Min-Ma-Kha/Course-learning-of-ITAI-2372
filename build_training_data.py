"""
build_training_data.py - Creates the labeled dataset used to train the
expense categorizer.

Course: ITAI 2372 - Module 04 (AI in Finance)
Project: NextDollar Compass

WHY SYNTHETIC DATA?
-------------------
Real bank transactions are private financial data, so a student project
should not train on them. Instead, this script builds a realistic
*synthetic* dataset:

  1. Each subcategory has a list of real-world merchant names
     (e.g. "Groceries" -> HEB, Kroger, Aldi...) and plain-English phrases
     people type (e.g. "weekly groceries").
  2. The script writes each merchant the way banks print them, with random
     prefixes, store numbers and city names, for example:
         "POS PURCHASE WHATABURGER #1043 KATY TX"
         "SQ *BLUE BOTTLE COFFEE HOUSTON TX"
  3. It also writes the plain-English versions, because people typing their
     own expenses write "netflix" or "electric bill", not bank codes.

Each row is labeled with its subcategory, and also records which merchant
it came from ("merchant" column). model_training.py uses that column to test
the model on merchants it has never seen - an honest test of how well it
generalizes.

Run:  python build_training_data.py      (writes data/training_transactions.csv)
"""

import csv
import random
from pathlib import Path

from categories import ALL_SUBCATEGORIES

random.seed(2372)  # fixed seed -> the same dataset every time (reproducible)

OUT_PATH = Path(__file__).parent / "data" / "training_transactions.csv"

# ---------------------------------------------------------------------------
# Merchants (as banks print them) and phrases (as people type them)
# ---------------------------------------------------------------------------
MERCHANTS: dict[str, list[str]] = {
    "Rent": ["CAMDEN PROPERTY TRUST", "GREYSTAR RENT", "BILT RENT PAYMENT", "AVALON APARTMENTS",
             "MAA APARTMENT RENT", "RENTCAFE PAYMENT", "APPFOLIO RENT", "ZILLOW RENTAL PAYMENT"],
    "Mortgage Payment": ["ROCKET MORTGAGE", "MR COOPER MORTGAGE", "PENNYMAC LOAN SERVICES", "LOANDEPOT MTG PMT",
                         "WELLS FARGO HOME MTG", "CHASE MORTGAGE PMT", "FREEDOM MORTGAGE", "UWM MORTGAGE PAYMENT"],
    "Property Tax & HOA": ["HARRIS COUNTY TAX OFFICE", "FORT BEND COUNTY TAX", "HOA DUES PAYMENT",
                           "FIRSTSERVICE RESIDENTIAL HOA", "ASSOCIA HOA", "PROPERTY TAX PAYMENT", "WALLER COUNTY TAX"],
    "Home Insurance": ["LEMONADE HOME INSURANCE", "HIPPO HOME INS", "KIN INSURANCE HOME", "HOMEOWNERS INS PREMIUM",
                       "TEXAS WINDSTORM INS", "RENTERS INSURANCE LEMONADE", "ASSURANT RENTERS INS"],
    "Home Repair & Maintenance": ["THE HOME DEPOT", "LOWES HOME IMPROVEMENT", "ACE HARDWARE", "MENARDS",
                                  "TERMINIX PEST CONTROL", "ABC HOME SERVICES", "HVAC REPAIR SERVICE", "PLUMBER SERVICE CALL"],
    "Electricity": ["RELIANT ENERGY", "TXU ENERGY", "GEXA ENERGY", "DIRECT ENERGY", "GREEN MOUNTAIN ENERGY",
                    "4CHANGE ENERGY", "CIRRO ENERGY", "ENTERGY ELECTRIC"],
    "Water & Trash": ["CITY OF HOUSTON WATER", "CITY OF KATY UTILITIES", "REPUBLIC SERVICES TRASH", "WASTE MANAGEMENT",
                      "MUD DISTRICT WATER BILL", "AQUA TEXAS WATER", "CITY WATER SEWER"],
    "Natural Gas": ["CENTERPOINT ENERGY GAS", "ATMOS ENERGY", "TEXAS GAS SERVICE", "SIEMPRE VERDE GAS UTILITY",
                    "NATURAL GAS UTILITY BILL", "SPIRE GAS"],
    "Internet": ["COMCAST XFINITY INTERNET", "AT&T INTERNET FIBER", "SPECTRUM INTERNET", "GOOGLE FIBER",
                 "FRONTIER INTERNET", "T-MOBILE HOME INTERNET", "STARLINK INTERNET"],
    "Mobile Phone": ["T-MOBILE WIRELESS", "VERIZON WIRELESS", "AT&T WIRELESS BILL", "CRICKET WIRELESS",
                     "METRO BY T-MOBILE", "MINT MOBILE", "VISIBLE WIRELESS", "BOOST MOBILE"],
    "Fuel": ["SHELL OIL", "EXXONMOBIL", "CHEVRON", "VALERO", "BUC-EES", "QUIKTRIP", "MURPHY USA", "CIRCLE K FUEL",
             "SUNOCO", "RACETRAC"],
    "Car Insurance": ["PROGRESSIVE INSURANCE", "GEICO AUTO", "STATE FARM AUTO", "ALLSTATE AUTO INS", "USAA AUTO INS",
                      "ROOT INSURANCE", "LIBERTY MUTUAL AUTO"],
    "Car Maintenance & Repair": ["JIFFY LUBE", "DISCOUNT TIRE", "AUTOZONE", "OREILLY AUTO PARTS", "FIRESTONE COMPLETE AUTO",
                                 "TAKE 5 OIL CHANGE", "PEP BOYS", "VALVOLINE INSTANT OIL", "MEINEKE CAR CARE"],
    "Rideshare & Taxi": ["UBER TRIP", "LYFT RIDE", "UBER *TRIP HELP.UBER.COM", "LYFT *RIDE SUN", "YELLOW CAB HOUSTON",
                         "ALTO RIDESHARE"],
    "Public Transit": ["METRO HOUSTON Q CARD", "HOUSTON METRORAIL", "DART TRANSIT", "MTA METROCARD", "CAPMETRO TRANSIT",
                       "AMTRAK TRAIN"],
    "Parking & Tolls": ["HCTRA EZ TAG", "TXTAG TOLL", "PARKMOBILE", "SP PLUS PARKING", "FORT BEND TOLL ROAD",
                        "PREMIUM PARKING", "AIRPORT PARKING IAH"],
    "Groceries": ["HEB GROCERY", "KROGER", "WALMART SUPERCENTER", "COSTCO WHSE", "ALDI", "FIESTA MART", "SPROUTS FARMERS MKT",
                  "TRADER JOES", "WHOLE FOODS MKT", "INSTACART", "SAMS CLUB", "99 RANCH MARKET", "PATEL BROTHERS",
                  "H MART"],
    "Restaurants": ["OLIVE GARDEN", "CHILIS GRILL", "TEXAS ROADHOUSE", "PAPPASITOS CANTINA", "PAPPADEAUX SEAFOOD",
                    "THE CHEESECAKE FACTORY", "PF CHANGS", "BJS RESTAURANT", "IHOP", "DENNYS", "PHO SAIGON RESTAURANT",
                    "TORCHYS TACOS"],
    "Fast Food": ["MCDONALDS", "WHATABURGER", "CHICK-FIL-A", "TACO BELL", "WENDYS", "POPEYES", "RAISING CANES",
                  "SUBWAY", "JACK IN THE BOX", "SONIC DRIVE IN", "BURGER KING", "CHIPOTLE"],
    "Coffee & Snacks": ["STARBUCKS", "DUNKIN", "DUTCH BROS COFFEE", "SHIPLEY DO-NUTS", "KOLACHE FACTORY",
                        "SHARETEA BOBA", "SWIG DRINKS", "TROPICAL SMOOTHIE"],
    "Food Delivery": ["DOORDASH", "UBER EATS", "UBER *EATS PENDING", "GRUBHUB", "POSTMATES", "DD *DOORDASH DASHPASS"],
    "Health Insurance": ["BLUE CROSS BLUE SHIELD TX", "AMBETTER HEALTH", "UNITEDHEALTHCARE PREMIUM", "AETNA HEALTH",
                         "CIGNA HEALTHCARE", "OSCAR HEALTH INS"],
    "Pharmacy": ["CVS PHARMACY", "WALGREENS", "HEB PHARMACY", "WALMART PHARMACY", "KROGER PHARMACY",
                 "GOODRX PHARMACY", "AMAZON PHARMACY"],
    "Doctor & Dental": ["MEMORIAL HERMANN", "HOUSTON METHODIST", "KELSEY-SEYBOLD CLINIC", "ASPEN DENTAL",
                        "QUEST DIAGNOSTICS", "NEXT LEVEL URGENT CARE", "TEXAS CHILDRENS", "LABCORP", "BRIGHT NOW DENTAL"],
    "Gym & Fitness": ["PLANET FITNESS", "LA FITNESS", "24 HOUR FITNESS", "CRUNCH FITNESS", "ANYTIME FITNESS",
                      "LIFE TIME FITNESS", "ORANGETHEORY"],
    "Clothing": ["OLD NAVY", "ROSS STORES", "TJ MAXX", "MARSHALLS", "NIKE STORE", "H&M", "MACYS", "BURLINGTON",
                 "SHEIN", "ACADEMY APPAREL"],
    "Electronics": ["BEST BUY", "APPLE STORE", "MICRO CENTER", "SAMSUNG.COM", "B&H PHOTO", "NEWEGG"],
    "Household Supplies": ["DOLLAR TREE", "DOLLAR GENERAL", "FAMILY DOLLAR", "TARGET", "BED BATH BEYOND",
                           "THE CONTAINER STORE", "FIVE BELOW"],
    "Online Shopping": ["AMAZON.COM", "AMZN MKTP US", "EBAY", "ETSY", "TEMU", "WALMART.COM", "WAYFAIR"],
    "Beauty & Personal Care": ["GREAT CLIPS", "SUPERCUTS", "SALLY BEAUTY", "ULTA BEAUTY", "SEPHORA", "BARBER SHOP",
                               "NAIL SALON SPA", "BATH AND BODY WORKS"],
    "Streaming & Subscriptions": ["NETFLIX.COM", "SPOTIFY", "HULU", "DISNEY PLUS", "YOUTUBE PREMIUM", "MAX STREAMING",
                                  "APPLE.COM/BILL ICLOUD", "AMAZON PRIME MEMBERSHIP", "PARAMOUNT PLUS", "PEACOCK TV",
                                  "CHATGPT SUBSCRIPTION", "CLAUDE.AI SUBSCRIPTION"],
    "Video Games": ["STEAM PURCHASE", "PLAYSTATION NETWORK", "XBOX GAME PASS", "NINTENDO ESHOP", "GAMESTOP",
                    "EPIC GAMES STORE"],
    "Movies & Events": ["AMC THEATRES", "CINEMARK", "REGAL CINEMAS", "TICKETMASTER", "STUBHUB", "TOPGOLF",
                        "SPACE CENTER HOUSTON", "HOUSTON RODEO TICKETS"],
    "Hobbies & Sports": ["MICHAELS STORES", "HOBBY LOBBY", "GUITAR CENTER", "ACADEMY SPORTS", "BASS PRO SHOPS",
                         "DICKS SPORTING GOODS", "REI CO-OP"],
    "Childcare": ["KINDERCARE", "PRIMROSE SCHOOL", "BRIGHT HORIZONS", "LA PETITE ACADEMY", "DAYCARE TUITION",
                  "GODDARD SCHOOL"],
    "Tuition & Books": ["HOUSTON COMMUNITY COLLEGE", "LONE STAR COLLEGE", "UNIVERSITY OF HOUSTON", "CHEGG",
                        "PEARSON EDUCATION", "COURSERA", "BARNES NOBLE COLLEGE", "UDEMY"],
    "Pets": ["PETCO", "PETSMART", "CHEWY.COM", "BANFIELD PET HOSPITAL", "VCA ANIMAL HOSPITAL", "ROVER PET SITTING"],
    "Charity & Donations": ["AMERICAN RED CROSS", "ST JUDE CHILDRENS", "GOFUNDME", "ISLAMIC RELIEF USA", "UNICEF USA",
                            "HOUSTON FOOD BANK", "SALVATION ARMY", "CHURCH TITHE ONLINE", "MASJID DONATION",
                            "TEMPLE DONATION", "LAUNCHGOOD"],
    "Gifts": ["1-800-FLOWERS", "EDIBLE ARRANGEMENTS", "HALLMARK", "GIFT CARD PURCHASE", "PARTY CITY", "SHUTTERFLY"],
    "Flights": ["UNITED AIRLINES", "SOUTHWEST AIRLINES", "AMERICAN AIRLINES", "SPIRIT AIRLINES", "DELTA AIR LINES",
                "EXPEDIA FLIGHT", "QATAR AIRWAYS", "TURKISH AIRLINES"],
    "Hotels & Lodging": ["MARRIOTT HOTEL", "HILTON HOTELS", "AIRBNB", "HOLIDAY INN", "BOOKING.COM HOTEL", "HAMPTON INN",
                         "VRBO RENTAL"],
    "Bank Fees": ["OVERDRAFT FEE", "MONTHLY SERVICE FEE", "ATM FEE", "FOREIGN TRANSACTION FEE", "WIRE TRANSFER FEE",
                  "NSF RETURNED ITEM FEE", "LATE PAYMENT FEE"],
    "Debt Payments": ["CAPITAL ONE PAYMENT", "CHASE CARD PAYMENT", "DISCOVER CARD PMT", "CITI CARD PAYMENT",
                      "TOYOTA FINANCIAL SVCS", "ALLY AUTO PAYMENT", "NAVIENT STUDENT LOAN", "NELNET STUDENT LOAN",
                      "SYNCHRONY BANK PMT", "AMEX AUTOPAY", "AFFIRM PAYMENT", "KLARNA PAYMENT"],
    "Savings & Investing": ["TRANSFER TO SAVINGS", "FIDELITY INVESTMENTS", "VANGUARD BUY", "ROBINHOOD", "COINBASE",
                            "WAHED INVEST", "ACORNS INVEST", "CHARLES SCHWAB", "ALLY SAVINGS TRANSFER", "BETTERMENT"],
    "Life Insurance": ["NORTHWESTERN MUTUAL LIFE", "HAVEN LIFE", "LADDER LIFE INS", "TERM LIFE PREMIUM",
                       "BANNER LIFE", "LIFE INSURANCE PREMIUM"],
    "Money Transfers": ["ZELLE TO", "VENMO PAYMENT", "CASH APP", "REMITLY", "WESTERN UNION", "WISE TRANSFER",
                        "MONEYGRAM", "XOOM TRANSFER", "PAYPAL TRANSFER"],
}

# What people actually type when they list their own expenses.
PHRASES: dict[str, list[str]] = {
    "Rent": ["rent", "apartment rent", "monthly rent", "house rent", "rent payment", "room rent"],
    "Mortgage Payment": ["mortgage", "house payment", "mortgage payment", "home loan payment"],
    "Property Tax & HOA": ["property tax", "hoa", "hoa fees", "homeowners association dues", "county taxes"],
    "Home Insurance": ["home insurance", "homeowners insurance", "renters insurance", "windstorm insurance"],
    "Home Repair & Maintenance": ["home repairs", "lawn care", "pest control", "ac repair", "plumbing repair",
                                  "yard work", "home maintenance"],
    "Electricity": ["electric bill", "electricity", "light bill", "power bill"],
    "Water & Trash": ["water bill", "trash pickup", "water and sewer", "garbage service"],
    "Natural Gas": ["gas bill for house", "natural gas", "gas utility", "heating gas bill"],
    "Internet": ["internet", "wifi", "home internet", "broadband", "fiber internet"],
    "Mobile Phone": ["phone bill", "cell phone", "mobile plan", "cellphone bill", "phone plan"],
    "Fuel": ["gas for car", "gasoline", "fuel", "gas station", "filling up the car", "diesel"],
    "Car Insurance": ["car insurance", "auto insurance", "vehicle insurance"],
    "Car Maintenance & Repair": ["oil change", "car repair", "new tires", "car wash", "car maintenance",
                                 "brake repair", "car registration"],
    "Rideshare & Taxi": ["uber rides", "lyft", "taxi", "rideshare"],
    "Public Transit": ["bus pass", "metro card", "train ticket", "public transportation"],
    "Parking & Tolls": ["tolls", "toll road", "parking", "ez tag", "parking garage"],
    "Groceries": ["groceries", "grocery shopping", "food shopping", "supermarket", "weekly groceries", "costco run"],
    "Restaurants": ["eating out", "restaurants", "dinner out", "date night dinner", "lunch at restaurant", "dining out"],
    "Fast Food": ["fast food", "drive thru", "burgers", "quick lunch", "takeout"],
    "Coffee & Snacks": ["coffee", "coffee shop", "snacks", "boba tea", "donuts", "energy drinks"],
    "Food Delivery": ["food delivery", "delivery apps", "ordered food", "doordash orders"],
    "Health Insurance": ["health insurance", "medical insurance", "dental insurance", "vision insurance"],
    "Pharmacy": ["medicine", "prescriptions", "pharmacy", "vitamins"],
    "Doctor & Dental": ["doctor visit", "dentist", "copay", "medical bills", "eye doctor", "urgent care visit",
                        "therapy copay"],
    "Gym & Fitness": ["gym membership", "gym", "fitness class", "yoga class", "personal trainer"],
    "Clothing": ["clothes", "shoes", "clothing", "new outfit", "work uniform"],
    "Electronics": ["electronics", "new laptop", "headphones", "phone case", "computer parts"],
    "Household Supplies": ["household supplies", "cleaning supplies", "toilet paper", "laundry detergent",
                           "home goods", "paper towels"],
    "Online Shopping": ["amazon", "online shopping", "amazon orders", "online orders"],
    "Beauty & Personal Care": ["haircut", "barber", "nails", "makeup", "skincare", "hair salon", "toiletries"],
    "Streaming & Subscriptions": ["netflix", "spotify", "streaming", "subscriptions", "disney plus", "icloud storage",
                                  "youtube premium", "amazon prime", "music subscription", "app subscriptions"],
    "Video Games": ["video games", "games", "playstation", "xbox", "game pass", "steam games"],
    "Movies & Events": ["movies", "concert tickets", "movie theater", "sports tickets", "events", "bowling"],
    "Hobbies & Sports": ["hobbies", "craft supplies", "fishing gear", "sports equipment", "camping gear", "art supplies"],
    "Childcare": ["daycare", "babysitter", "childcare", "after school care", "nanny"],
    "Tuition & Books": ["tuition", "textbooks", "school fees", "college classes", "online course", "certification exam"],
    "Pets": ["dog food", "vet bill", "pet supplies", "cat food", "pet insurance", "grooming for dog"],
    "Charity & Donations": ["donation", "charity", "tithe", "zakat", "sadaqah", "church offering", "mosque donation",
                            "giving to charity"],
    "Gifts": ["gifts", "birthday gift", "christmas gifts", "eid gifts", "wedding gift", "flowers for mom"],
    "Flights": ["plane tickets", "flight", "airfare", "flight home"],
    "Hotels & Lodging": ["hotel", "airbnb stay", "vacation rental", "motel"],
    "Bank Fees": ["bank fees", "overdraft fee", "atm fees", "account maintenance fee"],
    "Debt Payments": ["credit card payment", "car payment", "student loan", "loan payment", "auto loan",
                      "personal loan payment", "buy now pay later"],
    "Savings & Investing": ["savings", "investing", "401k", "roth ira", "emergency fund deposit", "stock purchase",
                            "transfer to savings account"],
    "Life Insurance": ["life insurance", "term life insurance", "whole life policy"],
    "Money Transfers": ["zelle", "venmo", "cash app", "send money home", "money transfer", "remittance",
                        "sent money to family"],
}

PREFIXES = ["", "", "", "POS PURCHASE ", "DEBIT CARD PURCHASE ", "CHECKCARD ", "PURCHASE AUTHORIZED ON 10/14 ",
            "RECURRING PAYMENT ", "ACH DEBIT ", "VISA DDA PUR ", "PAYPAL *", "SQ *", "TST* "]
CITIES = ["HOUSTON TX", "KATY TX", "CYPRESS TX", "SUGAR LAND TX", "PEARLAND TX", "RICHMOND TX", "BROOKSHIRE TX",
          "WALLER TX", "SPRING TX", "AUSTIN TX", "DALLAS TX", "SAN ANTONIO TX", "", "", ""]
PHRASE_TEMPLATES = ["{p}", "{p}", "my {p}", "{p} bill", "{p} this month", "monthly {p}", "{p} payment", "{P}"]


def bank_style(merchant: str) -> str:
    """Write a merchant name the messy way a bank statement prints it."""
    text = random.choice(PREFIXES) + merchant
    if random.random() < 0.55:
        text += f" #{random.randint(100, 9999)}"
    city = random.choice(CITIES)
    if city:
        text += f" {city}"
    if random.random() < 0.15:
        text += f" {random.randint(1, 12):02d}/{random.randint(1, 28):02d}"
    # Banks are inconsistent about case.
    return text.upper() if random.random() < 0.8 else text.title()


def human_style(phrase: str) -> str:
    template = random.choice(PHRASE_TEMPLATES)
    return template.format(p=phrase, P=phrase.title())


def build(rows_per_merchant: int = 10, rows_per_phrase: int = 6) -> list[dict]:
    rows = []
    for sub in ALL_SUBCATEGORIES:
        for merchant in MERCHANTS[sub]:
            for _ in range(rows_per_merchant):
                rows.append({"text": bank_style(merchant), "label": sub, "merchant": merchant, "style": "bank"})
        for phrase in PHRASES[sub]:
            for _ in range(rows_per_phrase):
                rows.append({"text": human_style(phrase), "label": sub, "merchant": "phrase:" + phrase,
                             "style": "typed"})
    random.shuffle(rows)
    return rows


def main() -> None:
    missing = [s for s in ALL_SUBCATEGORIES if s not in MERCHANTS or s not in PHRASES]
    if missing:
        raise SystemExit(f"Every subcategory needs merchants and phrases. Missing: {missing}")
    rows = build()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["text", "label", "merchant", "style"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"[INFO] Wrote {len(rows):,} labeled rows across {len(ALL_SUBCATEGORIES)} subcategories -> {OUT_PATH}")


if __name__ == "__main__":
    main()
