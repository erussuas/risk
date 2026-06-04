# EnergyCAP Late Fee & Service Disconnection Risk Dashboard

A Streamlit app for analyzing EnergyCAP Bill Transfer Format exports, especially custom reports containing AP fields such as `AP Status`, `AP Date`, `Prior Balance`, `Late Fee`, `Amount Due`, and `Pay Amount`.

## What it does

The app creates five main views:

1. **Summary**
   - Bills loaded, total spend, total late fees
   - Bills not exported to AP
   - Accounts with prior balances
   - Monthly trend of late fees, prior balances, and AP queue
   - Top highest-risk accounts

2. **AP Processing Analysis**
   - AP status breakdown
   - Average AP lag by vendor, where AP Date exists
   - Oldest and highest-value bills not exported to AP

3. **Prior Balance & Late Fees**
   - Prior balance by vendor
   - Late fees by vendor
   - Accounts with recurring prior balances or late fees

4. **Vendor / Site Risk**
   - Vendor, site, or commodity scorecard
   - Risk heatmap by month

5. **Recommended Actions**
   - Prioritized operational work queue
   - Recommended next action per account/bill
   - Downloadable Excel action register

6. **Data Quality**
   - Detected column mapping
   - Missing expected fields
   - Normalized data preview

## How to run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## How to deploy on Streamlit Community Cloud

1. Create a GitHub repository.
2. Upload `app.py`, `requirements.txt`, and this `README.md` to the repo root.
3. In Streamlit Community Cloud, create a new app from the GitHub repo.
4. Set the main file path to `app.py`.
5. Deploy.

## Recommended EnergyCAP export

Use the custom report similar to `Custom-ENEL01-Bill Transfer Format` with:

- 18–24 months of history for historical scoring
- Current month export for AP queue visibility
- All active accounts, commodities, and vendors
- Excel format

The most useful fields are:

- Account Code
- Vendor Code / Vendor Name
- Place Code / Site Name
- Commodity Code
- Billing Period
- End Date
- Cost
- Prior Balance
- Late Fee
- Amount Due
- Pay Amount
- AP Status
- AP Date

## Risk logic

Risk score is based on:

- Prior Balance present
- Late Fee present
- AP Status not exported / blank / No
- Payment shortfall between Amount Due and Pay Amount
- Bill age where due date or end date suggests the bill is old
- High-value bills still not exported to AP

This is an operational prioritization model, not a utility-confirmed disconnect notice feed. For actual disconnection notices, the best source remains vendor communications, lockbox/email intake, or utility portal status.
