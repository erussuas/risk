import re
from io import BytesIO
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="EnergyCAP AP Risk Dashboard", layout="wide")

# -----------------------------
# Helpers
# -----------------------------

def clean_col(x: object) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip().replace("\n", " ")
    s = re.sub(r"\s+", " ", s)
    return s


def norm_key(s: object) -> str:
    s = clean_col(s).lower()
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s

CANONICAL_ALIASES: Dict[str, List[str]] = {
    "place_code": ["placecode", "place", "sitecode", "siteid", "facilitycode"],
    "place_name": ["placename", "sitename", "facilityname"],
    "meter_code": ["metercode", "meter", "meterid", "meternumber"],
    "commodity_code": ["commoditycode", "commodity", "service", "servicetype"],
    "account_code": ["accountcode", "account", "accountnumber", "utilityaccount", "acctnumber", "acctno"],
    "vendor_code": ["vendorcode", "vendor", "utilityvendor", "utility", "supplier"],
    "vendor_name": ["vendorname", "utilityname", "suppliername"],
    "bill_id": ["billid", "energycapbillid", "billnumber", "invoiceid", "invoicenumber"],
    "billing_period": ["billingperiod", "billperiod", "period", "accountingperiod"],
    "rate_schedule": ["rateschedule", "rate", "tariff"],
    "start_date": ["startdate", "servicestart", "fromdate", "begindate"],
    "end_date": ["enddate", "serviceend", "todate"],
    "days": ["days", "billingdays", "servicedays"],
    "native_use": ["nativeuse", "use", "usage", "consumption"],
    "demand": ["demand", "kw", "billingdemand"],
    "cost": ["cost", "currentcharges", "billamount", "invoiceamount", "totalcost"],
    "prior_balance": ["priorbalance", "previousbalance", "balanceforward", "pastdue", "pastduebalance"],
    "late_fee": ["latefee", "latecharge", "penalty", "financecharge"],
    "amount_due": ["amountdueecbc", "amountdue", "totalamountdue", "netamountdue"],
    "pay_amount": ["payamount", "paymentamount", "amountpaid", "payment"],
    "ap_status": ["apstatus", "apstatusyesno", "exportedtoap", "senttoap", "appaymentstatus"],
    "ap_date": ["apdate", "apexportdate", "paymentdate", "datepaid", "senttoapdate"],
    "due_date": ["duedate", "paymentduedate", "billduedate"],
    "entry_date": ["billentrydate", "entrydate", "importdate", "createddate"],
}

KNOWN_HEADER_KEYS = {v for vals in CANONICAL_ALIASES.values() for v in vals}


def detect_header_row(raw: pd.DataFrame, max_scan: int = 30) -> int:
    best_idx, best_score = 0, -1
    for i in range(min(max_scan, len(raw))):
        keys = [norm_key(x) for x in raw.iloc[i].tolist()]
        score = sum(1 for k in keys if k in KNOWN_HEADER_KEYS)
        # Bonus for distinctive report fields
        if "apstatus" in keys:
            score += 4
        if "priorbalance" in keys:
            score += 3
        if "latefee" in keys:
            score += 3
        if score > best_score:
            best_idx, best_score = i, score
    return best_idx


def map_columns(columns: List[str]) -> Dict[str, str]:
    normalized_to_original = {norm_key(c): c for c in columns if clean_col(c)}
    mapping = {}
    for canonical, aliases in CANONICAL_ALIASES.items():
        for alias in aliases:
            if alias in normalized_to_original:
                mapping[canonical] = normalized_to_original[alias]
                break
    return mapping


def read_one_excel(uploaded_file) -> pd.DataFrame:
    raw = pd.read_excel(uploaded_file, header=None, dtype=object)
    header_row = detect_header_row(raw)
    df = pd.read_excel(uploaded_file, header=header_row, dtype=object)
    df.columns = [clean_col(c) for c in df.columns]
    df = df.loc[:, [c for c in df.columns if c and not c.lower().startswith("unnamed")]]
    df = df.dropna(how="all")
    df["source_file"] = getattr(uploaded_file, "name", "uploaded_file")
    return df


def parse_money(series: pd.Series) -> pd.Series:
    if series is None:
        return pd.Series(dtype=float)
    cleaned = series.astype(str).str.replace(r"[$,()]", "", regex=True).str.strip()
    cleaned = cleaned.replace({"": np.nan, "nan": np.nan, "None": np.nan})
    return pd.to_numeric(cleaned, errors="coerce").fillna(0.0)


def parse_num(series: pd.Series) -> pd.Series:
    if series is None:
        return pd.Series(dtype=float)
    return pd.to_numeric(series, errors="coerce")


def parse_date(series: pd.Series) -> pd.Series:
    if series is None:
        return pd.Series(dtype="datetime64[ns]")
    return pd.to_datetime(series, errors="coerce")


def normalize(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, str]]:
    mapping = map_columns(list(df.columns))
    out = pd.DataFrame(index=df.index)
    for canon in CANONICAL_ALIASES:
        src = mapping.get(canon)
        out[canon] = df[src] if src else np.nan
    out["source_file"] = df.get("source_file", "uploaded_file")

    text_cols = ["place_code", "place_name", "meter_code", "commodity_code", "account_code", "vendor_code", "vendor_name", "bill_id", "billing_period", "rate_schedule", "ap_status"]
    for c in text_cols:
        out[c] = out[c].astype(str).replace({"nan": "", "None": ""}).str.strip()

    for c in ["cost", "prior_balance", "late_fee", "amount_due", "pay_amount"]:
        out[c] = parse_money(out[c])
    for c in ["days", "native_use", "demand"]:
        out[c] = parse_num(out[c])
    for c in ["start_date", "end_date", "ap_date", "due_date", "entry_date"]:
        out[c] = parse_date(out[c])

    # Create usable period month.
    period_str = out["billing_period"].astype(str).str.extract(r"(\d{4})\D?(\d{2})", expand=True)
    out["period_month"] = pd.to_datetime(period_str[0] + "-" + period_str[1] + "-01", errors="coerce")
    out.loc[out["period_month"].isna(), "period_month"] = out.loc[out["period_month"].isna(), "end_date"].values.astype("datetime64[M]")

    out["account_key"] = out["vendor_code"].where(out["vendor_code"].ne(""), out["vendor_name"]) + " | " + out["account_code"]
    out["site_key"] = out["place_code"].where(out["place_code"].ne(""), out["place_name"])
    out["vendor_key"] = out["vendor_code"].where(out["vendor_code"].ne(""), out["vendor_name"])
    out["ap_status_norm"] = out["ap_status"].str.lower().str.strip()
    out["ap_not_exported"] = out["ap_status_norm"].isin(["no", "n", "false", "0", "", "none", "nan"])
    out["has_prior_balance"] = out["prior_balance"] > 0.01
    out["has_late_fee"] = out["late_fee"] > 0.01
    out["balance_gap"] = (out["amount_due"] - out["pay_amount"]).round(2)
    out["has_payment_shortfall"] = out["balance_gap"] > 0.01

    today = pd.Timestamp.today().normalize()
    anchor = out["due_date"].fillna(out["end_date"])
    out["bill_age_days"] = (today - anchor).dt.days
    out["ap_lag_days"] = (out["ap_date"] - out["end_date"]).dt.days
    out["entry_to_ap_days"] = (out["ap_date"] - out["entry_date"]).dt.days

    # Action/risk scoring at bill row level.
    out["risk_score"] = 0
    out.loc[out["has_prior_balance"], "risk_score"] += 30
    out.loc[out["has_late_fee"], "risk_score"] += 30
    out.loc[out["ap_not_exported"], "risk_score"] += 20
    out.loc[out["has_payment_shortfall"], "risk_score"] += 15
    out.loc[(out["ap_not_exported"]) & (out["bill_age_days"] >= 30), "risk_score"] += 20
    out.loc[(out["ap_not_exported"]) & (out["bill_age_days"] >= 45), "risk_score"] += 15
    out["risk_score"] = out["risk_score"].clip(0, 100)

    bins = [-1, 24, 49, 74, 100]
    labels = ["Low", "Medium", "High", "Critical"]
    out["risk_level"] = pd.cut(out["risk_score"], bins=bins, labels=labels).astype(str)

    def action(row):
        if row["has_prior_balance"] and row["has_late_fee"] and row["ap_not_exported"]:
            return "Escalate immediately: confirm payment/export and contact utility if needed"
        if row["has_prior_balance"] and row["ap_not_exported"]:
            return "Confirm AP export and open balance; prioritize before next bill cycle"
        if row["has_late_fee"]:
            return "Review root cause of late fee; verify payment timing and vendor remittance"
        if row["ap_not_exported"] and row["bill_age_days"] >= 30:
            return "Investigate why bill has not reached AP; resolve workflow blockage"
        if row["has_prior_balance"]:
            return "Validate whether balance is real, disputed, or timing-related"
        if row["ap_not_exported"]:
            return "Monitor AP export queue"
        return "No immediate action"

    out["recommended_action"] = out.apply(action, axis=1)
    return out, mapping


def dollars(x):
    try:
        return f"${x:,.0f}"
    except Exception:
        return "$0"


def pct(x):
    try:
        return f"{x:.1%}"
    except Exception:
        return "0.0%"


def export_excel(dfs: Dict[str, pd.DataFrame]) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        for name, data in dfs.items():
            safe_name = name[:31]
            data.to_excel(writer, index=False, sheet_name=safe_name)
            ws = writer.sheets[safe_name]
            for idx, col in enumerate(data.columns):
                width = min(max(len(str(col)) + 2, 12), 42)
                ws.set_column(idx, idx, width)
    return output.getvalue()


# -----------------------------
# UI
# -----------------------------

st.title("EnergyCAP Late Fee & Service Disconnection Risk Dashboard")
st.caption("Upload one or more EnergyCAP Bill Transfer Format Excel exports. A 18–24 month export creates the best historical risk view; a current-month export helps identify bills not yet exported to AP.")

with st.sidebar:
    st.header("Upload")
    files = st.file_uploader("EnergyCAP Excel report(s)", type=["xlsx", "xls"], accept_multiple_files=True)
    st.header("Risk settings")
    high_value_threshold = st.number_input("High-value unexported bill threshold", min_value=0, value=10000, step=1000)
    old_bill_days = st.number_input("Old unexported bill age threshold", min_value=1, value=30, step=1)
    st.markdown("**Expected useful fields:** AP Status, AP Date, Prior Balance, Late Fee, Amount Due, Pay Amount, Vendor, Account, Site, Commodity, End Date.")

if not files:
    st.info("Upload the Custom ENEL01 Bill Transfer Format report to begin.")
    st.stop()

frames = []
errors = []
for f in files:
    try:
        frames.append(read_one_excel(f))
    except Exception as e:
        errors.append(f"{f.name}: {e}")

if errors:
    st.warning("Some files could not be read:\n" + "\n".join(errors))

if not frames:
    st.error("No usable files were loaded.")
    st.stop()

raw_all = pd.concat(frames, ignore_index=True)
data, mapping = normalize(raw_all)

# Dynamic recalculation for user threshold.
data.loc[(data["ap_not_exported"]) & (data["cost"] >= high_value_threshold), "risk_score"] = (data["risk_score"] + 10).clip(0, 100)
data.loc[(data["ap_not_exported"]) & (data["bill_age_days"] >= old_bill_days), "risk_score"] = (data["risk_score"] + 10).clip(0, 100)
data["risk_level"] = pd.cut(data["risk_score"], bins=[-1, 24, 49, 74, 100], labels=["Low", "Medium", "High", "Critical"]).astype(str)

valid_account = data["account_code"].ne("")
filtered = data[valid_account].copy() if valid_account.any() else data.copy()

# Account-level rollup
acct = filtered.groupby(["account_key", "vendor_key", "site_key", "commodity_code"], dropna=False).agg(
    bills=("bill_id", "count"),
    spend=("cost", "sum"),
    prior_balance_total=("prior_balance", "sum"),
    prior_balance_bills=("has_prior_balance", "sum"),
    late_fee_total=("late_fee", "sum"),
    late_fee_bills=("has_late_fee", "sum"),
    ap_not_exported_bills=("ap_not_exported", "sum"),
    max_bill_age_days=("bill_age_days", "max"),
    avg_ap_lag_days=("ap_lag_days", "mean"),
    avg_risk_score=("risk_score", "mean"),
    max_risk_score=("risk_score", "max"),
).reset_index()
acct["prior_balance_rate"] = acct["prior_balance_bills"] / acct["bills"].replace(0, np.nan)
acct["late_fee_rate"] = acct["late_fee_bills"] / acct["bills"].replace(0, np.nan)
acct["priority_score"] = (
    acct["max_risk_score"] * 0.50
    + acct["prior_balance_rate"].fillna(0) * 20
    + acct["late_fee_rate"].fillna(0) * 20
    + np.minimum(acct["spend"] / max(high_value_threshold, 1), 3) * 5
).round(1).clip(0, 100)
acct["priority"] = pd.cut(acct["priority_score"], bins=[-1, 24, 49, 74, 100], labels=["Monitor", "Medium", "High", "Critical"]).astype(str)
acct = acct.sort_values(["priority_score", "late_fee_total", "prior_balance_total"], ascending=False)

# Recommended actions table
recommend = filtered[filtered["risk_score"] >= 25].copy()
recommend = recommend.sort_values(["risk_score", "prior_balance", "late_fee", "cost"], ascending=False)
recommend_cols = [
    "risk_level", "risk_score", "recommended_action", "vendor_key", "account_code", "site_key", "commodity_code",
    "billing_period", "end_date", "ap_status", "ap_date", "cost", "prior_balance", "late_fee", "amount_due", "pay_amount", "bill_age_days", "source_file"
]
recommend = recommend[[c for c in recommend_cols if c in recommend.columns]]

# Tabs
tabs = st.tabs(["Summary", "AP Processing Analysis", "Prior Balance & Late Fees", "Vendor / Site Risk", "Recommended Actions", "Data Quality"])

with tabs[0]:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Bills loaded", f"{len(filtered):,}")
    c2.metric("Total spend", dollars(filtered["cost"].sum()))
    c3.metric("Late fees", dollars(filtered["late_fee"].sum()))
    c4.metric("Bills not exported to AP", f"{int(filtered['ap_not_exported'].sum()):,}")
    c5.metric("Accounts with prior balance", f"{acct[acct['prior_balance_bills'] > 0]['account_key'].nunique():,}")

    left, right = st.columns([1.2, 1])
    with left:
        st.subheader("Monthly risk trend")
        trend = filtered.dropna(subset=["period_month"]).groupby("period_month").agg(
            late_fee_total=("late_fee", "sum"),
            prior_balance_total=("prior_balance", "sum"),
            not_exported=("ap_not_exported", "sum"),
        ).reset_index()
        if not trend.empty:
            fig = px.line(trend, x="period_month", y=["late_fee_total", "prior_balance_total", "not_exported"], markers=True)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No valid billing period/end date available for trend analysis.")
    with right:
        st.subheader("Top 10 highest-risk accounts")
        st.dataframe(acct.head(10), use_container_width=True, hide_index=True)

with tabs[1]:
    st.subheader("AP status and export timing")
    left, right = st.columns(2)
    status = filtered["ap_status"].replace("", "Blank").value_counts().reset_index()
    status.columns = ["AP Status", "Bills"]
    with left:
        st.plotly_chart(px.bar(status, x="AP Status", y="Bills", text="Bills"), use_container_width=True)
    with right:
        lag = filtered.dropna(subset=["ap_lag_days"]).copy()
        if not lag.empty:
            lag_vendor = lag.groupby("vendor_key")["ap_lag_days"].mean().sort_values(ascending=False).head(20).reset_index()
            st.plotly_chart(px.bar(lag_vendor, x="vendor_key", y="ap_lag_days", title="Average AP lag by vendor"), use_container_width=True)
        else:
            st.info("AP Date is not populated enough to calculate AP lag.")

    st.subheader("Oldest / highest-value bills not exported to AP")
    queue = filtered[filtered["ap_not_exported"]].copy()
    queue = queue.sort_values(["bill_age_days", "cost"], ascending=False)
    st.dataframe(queue[[c for c in ["vendor_key", "account_code", "site_key", "commodity_code", "billing_period", "end_date", "cost", "ap_status", "bill_age_days", "source_file"] if c in queue.columns]].head(200), use_container_width=True, hide_index=True)

with tabs[2]:
    st.subheader("Prior balance and late fee patterns")
    c1, c2 = st.columns(2)
    vendor_pb = filtered.groupby("vendor_key").agg(prior_balance=("prior_balance", "sum"), late_fees=("late_fee", "sum"), bills=("bill_id", "count")).reset_index().sort_values("prior_balance", ascending=False).head(20)
    c1.plotly_chart(px.bar(vendor_pb, x="vendor_key", y="prior_balance", title="Prior balance by vendor"), use_container_width=True)
    c2.plotly_chart(px.bar(vendor_pb.sort_values("late_fees", ascending=False), x="vendor_key", y="late_fees", title="Late fees by vendor"), use_container_width=True)

    st.subheader("Accounts with recurring balances or late fees")
    recur = acct[(acct["prior_balance_bills"] > 0) | (acct["late_fee_bills"] > 0)].copy()
    st.dataframe(recur, use_container_width=True, hide_index=True)

with tabs[3]:
    st.subheader("Vendor / site risk scorecards")
    group_choice = st.radio("Group scorecard by", ["vendor_key", "site_key", "commodity_code"], horizontal=True)
    scorecard = filtered.groupby(group_choice).agg(
        bills=("bill_id", "count"),
        spend=("cost", "sum"),
        prior_balance_total=("prior_balance", "sum"),
        late_fee_total=("late_fee", "sum"),
        ap_not_exported_bills=("ap_not_exported", "sum"),
        avg_risk_score=("risk_score", "mean"),
        max_risk_score=("risk_score", "max"),
    ).reset_index().sort_values("max_risk_score", ascending=False)
    st.dataframe(scorecard, use_container_width=True, hide_index=True)

    st.subheader("Risk heatmap by month")
    heat = filtered.dropna(subset=["period_month"]).groupby([group_choice, "period_month"])["risk_score"].mean().reset_index()
    top_groups = scorecard[group_choice].head(15).tolist()
    heat = heat[heat[group_choice].isin(top_groups)]
    if not heat.empty:
        fig = px.density_heatmap(heat, x="period_month", y=group_choice, z="risk_score", histfunc="avg")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Not enough dated records to build a heatmap.")

with tabs[4]:
    st.subheader("Prioritized action register")
    st.caption("Use this tab as the operational work queue for AP, utility vendor management, and account owners.")
    risk_filter = st.multiselect("Risk levels", ["Critical", "High", "Medium", "Low"], default=["Critical", "High", "Medium"])
    rec_view = recommend[recommend["risk_level"].isin(risk_filter)] if risk_filter else recommend
    st.dataframe(rec_view, use_container_width=True, hide_index=True)

    export_bytes = export_excel({"Recommended Actions": rec_view, "Account Rollup": acct, "Normalized Data": filtered})
    st.download_button("Download action register", data=export_bytes, file_name="energycap_ap_risk_action_register.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

with tabs[5]:
    st.subheader("Column mapping detected")
    mapping_df = pd.DataFrame([{"Canonical field": k, "Source column": v} for k, v in mapping.items()])
    st.dataframe(mapping_df, use_container_width=True, hide_index=True)

    expected = ["account_code", "vendor_code", "billing_period", "end_date", "cost", "prior_balance", "late_fee", "amount_due", "pay_amount", "ap_status", "ap_date"]
    missing = [c for c in expected if c not in mapping]
    if missing:
        st.warning("Missing or undetected useful columns: " + ", ".join(missing))
    else:
        st.success("Core AP/bill-pay risk columns were detected.")

    st.subheader("Raw normalized preview")
    st.dataframe(filtered.head(200), use_container_width=True, hide_index=True)
