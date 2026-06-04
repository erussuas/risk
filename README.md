# EnergyCAP AP Risk Dashboard

Streamlit app for analyzing EnergyCAP custom Bill Transfer exports and optionally enriching them with EnergyCAP Report-03 setup/master data.

## Inputs

1. **Bill Transfer Format** exports (`Custom-ENEL01-Bill_Transfer_Format...xlsx`)
   - Core transaction file
   - Expected fields include: Account Code, Vendor Code, Bill ID, Billing Period, Start Date, End Date, Cost, Prior Balance, Late Fee, Amount Due, Pay Amount, AP Status, APDate.

2. **Optional Report-03 Setup Report** (`Report-03-Setup_Report_for_Accounts...xlsx`)
   - Master/enrichment file
   - Used for account status, vendor name, site/cost center, country, payment type, delivery method, bill frequency, export flag, GL/account mapping fields.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Typical workflow

1. Export 18-24 months of the Bill Transfer report from EnergyCAP.
2. Export Report-03 for active accounts.
3. Upload the Bill Transfer file(s) in the first uploader.
4. Upload Report-03 in the second uploader.
5. Review summary, AP processing, balances/late fees, vendor/site analysis, account master QA, and prioritized actions.
6. Download the recommended action register.

## Notes

- The app uses flexible header detection, so it should handle EnergyCAP exports with several blank rows before the header.
- The risk model is designed as an operational prioritization tool, not a definitive statement that service will be disconnected.
- Best results require a long enough bill history to detect recurring prior balances and repeated late fees.

## Scope rule

The app is scoped to **United States and Canada accounts only**, because those are the accounts relevant to the client AP file. When Report-03 is uploaded, records outside the US/Canada scope are excluded from KPIs, charts, scoring, QA tables, and recommended actions. The app uses Site Country first, then Account Country, then Vendor Country to determine scope. If no Report-03/country data is provided, the app keeps uploaded records but warns that country scope could not be verified.
