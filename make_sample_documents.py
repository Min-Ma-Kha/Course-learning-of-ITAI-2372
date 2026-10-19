"""
make_sample_documents.py - Creates FAKE documents for demos and testing.

Course: ITAI 2372 - Module 04 (AI in Finance)
Project: NextDollar Compass

Never demo a finance app with your own pay stub or statements. This script
makes four clearly-labeled sample PDFs (pay stub, credit-card statement,
mortgage statement, car-loan statement) plus a sample bank export CSV, all
for an invented person. Use them to try the upload buttons.

Run:  python make_sample_documents.py
"""

import csv
import random
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

OUT = Path(__file__).parent / "data" / "sample_documents"
NAME = "Jordan Rivera (SAMPLE)"


def _page(path: Path, title: str, issuer: str, rows: list[tuple[str, str]], extra: list[str] | None = None):
    c = canvas.Canvas(str(path), pagesize=letter)
    w, h = letter
    c.setFillColor(colors.HexColor("#b42318"))
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, h - 30, "SAMPLE DOCUMENT - FICTIONAL DATA FOR TESTING ONLY - NOT A REAL ACCOUNT")
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(40, h - 65, issuer)
    c.setFont("Helvetica", 12)
    c.drawString(40, h - 85, title)
    c.drawString(40, h - 102, f"Customer: {NAME}")
    c.drawString(40, h - 119, "Account: XXXX-XXXX-0000")
    y = h - 160
    c.setStrokeColor(colors.HexColor("#999999"))
    for label, value in rows:
        c.setFont("Helvetica", 11)
        c.drawString(50, y, label)
        c.setFont("Helvetica-Bold", 11)
        c.drawRightString(w - 60, y, value)
        c.line(50, y - 5, w - 60, y - 5)
        y -= 22
    if extra:
        y -= 10
        c.setFont("Helvetica", 9.5)
        for line in extra:
            c.drawString(50, y, line)
            y -= 14
    c.showPage()
    c.save()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    _page(OUT / "sample_paystub.pdf", "Earnings Statement", "Gulf Coast Logistics LLC", [
        ("Pay Period", "09/28/2026 - 10/11/2026"),
        ("Pay Date", "10/16/2026"),
        ("Pay Frequency", "Bi-Weekly"),
        ("Gross Pay", "$3,250.00"),
        ("Federal Income Tax", "$298.40"),
        ("Social Security", "$201.50"),
        ("Medicare", "$47.13"),
        ("Medical", "$92.00"),
        ("Dental", "$12.47"),
        ("401(k)", "$118.50"),
        ("Net Pay", "$2,480.00"),
    ], ["Texas has no state income tax, so no state withholding appears on this statement."])

    _page(OUT / "sample_credit_card_statement.pdf", "Monthly Statement - October 2026",
          "Lone Star Bank Rewards Card", [
              ("Previous Balance", "$4,402.18"),
              ("Payments and Credits", "-$300.00"),
              ("Purchases", "$66.84"),
              ("Interest Charged", "$80.98"),
              ("New Balance", "$4,250.00"),
              ("Minimum Payment Due", "$125.00"),
              ("Payment Due Date", "11/12/2026"),
              ("Credit Limit", "$6,000.00"),
          ], ["Interest Charge Calculation",
              "Purchase APR: 24.99%     Cash Advance APR: 29.99%",
              "Penalty APR: 29.99% (may apply if you make a late payment)",
              "Fees: Annual Fee: None     Late Payment: Up to $41",
              "Minimum Payment Warning: If you make only the minimum payment each period, you will pay more",
              "in interest and it will take you longer to pay off your balance."])

    _page(OUT / "sample_mortgage_statement.pdf", "Mortgage Statement", "Bayou City Mortgage Co.", [
        ("Statement Date", "10/01/2026"),
        ("Unpaid Principal Balance", "$238,000.00"),
        ("Interest Rate", "6.375%"),
        ("Principal and Interest", "$1,490.00"),
        ("Escrow (Taxes and Insurance)", "$560.00"),
        ("Regular Monthly Payment", "$2,050.00"),
        ("Remaining Term", "356 months"),
        ("Payment Due Date", "11/01/2026"),
    ])

    _page(OUT / "sample_car_loan_statement.pdf", "Auto Loan Statement", "Bluebonnet Auto Finance", [
        ("Vehicle", "2023 Toyota Camry"),
        ("Principal Balance", "$16,800.00"),
        ("Annual Percentage Rate", "7.40%"),
        ("Monthly Payment", "$410.00"),
        ("Payments Remaining", "46"),
        ("Next Payment Due", "11/05/2026"),
    ])

    random.seed(4)
    rows = []
    merchants = [("HEB GROCERY #512 KATY TX", 95, 160), ("SHELL OIL 57442 KATY TX", 35, 55),
                 ("WHATABURGER #1043 KATY TX", 9, 18), ("STARBUCKS STORE 10423", 5, 9),
                 ("NETFLIX.COM", 15.49, 15.49), ("AMZN MKTP US*2K4", 12, 60), ("DD *DOORDASH WINGSTOP", 18, 35),
                 ("RELIANT ENERGY RETAIL", 165, 165), ("PROGRESSIVE INS", 168, 168), ("CVS/PHARMACY #7710", 8, 25),
                 ("PLANET FITNESS CLUB", 25, 25), ("ROSS STORES #440", 25, 60), ("TXTAG TOLL", 10, 25)]
    for month in (8, 9):
        for desc, lo, hi in merchants:
            for _ in range(2 if lo < 40 else 1):
                day = random.randint(1, 28)
                rows.append([f"2026-{month:02d}-{day:02d}", desc, f"-{random.uniform(lo, hi):.2f}"])
        rows.append([f"2026-{month:02d}-15", "PAYROLL DEPOSIT GULF COAST LOGISTICS", "2480.00"])
    rows.sort()
    with (OUT / "sample_bank_export.csv").open("w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["Date", "Description", "Amount"])
        wr.writerows(rows)
    print(f"[INFO] Sample documents written to {OUT}")


if __name__ == "__main__":
    main()
