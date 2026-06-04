import io
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="EnergyCAP AP Risk Dashboard", layout="wide")

# -------------------------
# Helpers
# -------------------------

def clean_col(c: object) -> str:
    return " ".join(str(c).strip().replace("\n", " ").split())


def norm_col(c: object) -> str:
    s = clean_col(c).lower()
    keep = []
    for ch in s:
        keep.append(ch if ch.isalnum() else "_")
    return "_".join("".join(keep).split("_"))


def find_header_row(raw: pd.DataFrame, required_tokens: List[str], max_scan: int = 20) -> int:
    best_row = 0
    best_score = -1
    tokens = [t.lower() for t in required_tokens]
    for i in range(min(max_scan, len(raw))):
        vals = [clean_col(v).lower() for v in raw.iloc[i].tolist() if pd.notna(v)]
        joined = " | ".join(vals)
        score = sum(1 for t in tokens if t in joined)
        if score > best_score:
            best_score = score
            best_row = i
    return best_row


def read_energycap_excel(file, kind: str) -> pd.DataFrame:
    """Read EnergyCAP Excel with flexible header detection."""
    xls = pd.ExcelFile(file)
    sheet = "Sheet1" if "Sheet1" in xls.sheet_names else xls.sheet_names[0]
    raw = pd.read_excel(file, sheet_name=sheet, header=None)
    if kind == "bill":
        header_row = find_header_row(raw, ["Account Code", "Bill ID", "AP Status", "Billing Period", "Vendor Code"])
    else:
        header_row = find_header_row(raw, ["Account Number", "Vendor Name", "Cost Center", "Export Flag", "Meter Code"])
    headers = [clean_col(x) for x in raw.iloc[header_row].tolist()]
    df = raw.iloc[header_row + 1 :].copy()
    df.columns = headers
    df = df.dropna(how="all")
    df = df.loc[:, [c for c in df.columns if c and not str(c).lower().startswith("unnamed")]]
    df.columns = [clean_col(c) for c in df.columns]
    return df


def coalesce_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    nmap = {norm_col(c): c for c in df.columns}
    for cand in candidates:
        nc = norm_col(cand)
        if nc in nmap:
            return nmap[nc]
    # fuzzy contains fallback
    for cand in candidates:
        nc = norm_col(cand)
        for k, v in nmap.items():
            if nc in k or k in nc:
                return v
    return None


def to_num(s):
    if s is None:
        return pd.Series(dtype=float)
    return pd.to_numeric(s.astype(str).str.replace("$", "", regex=False).str.replace(",", "", regex=False).replace({"nan": np.nan, "None": np.nan, "": np.nan}), errors="coerce")


def parse_dates(s):
    return pd.to_datetime(s, errors="coerce")


def normalize_bill(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    col = lambda names: coalesce_col(df, names)
    mapping = {
        "place_code": col(["Place Code", "Place"]),
        "meter_code": col(["Meter Code", "Meter"]),
        "commodity_code": col(["Commodity Code", "Commodity"]),
        "account_code": col(["Account Code", "Account Number", "Account"]),
        "vendor_code": col(["Vendor Code", "Vendor"]),
        "cost_center_code": col(["C Ctr Code", "Cost Center Code"]),
        "bill_id": col(["Bill ID"]),
        "billing_period": col(["Billing Period"]),
        "rate_schedule": col(["Rate Schedule"]),
        "start_date": col(["Start Date", "Service Start"]),
        "end_date": col(["End Date", "Service End"]),
        "days": col(["Days"]),
        "native_use": col(["Native Use"]),
        "demand": col(["Demand"]),
        "common_use": col(["Common Use"]),
        "cost": col(["Cost"]),
        "prior_balance": col(["Prior Balance"]),
        "late_fee": col(["Late Fee"]),
        "amount_due": col(["Amount Due (ECBC)", "Amount Due"]),
        "pay_amount": col(["Pay Amount"]),
        "ap_status": col(["AP Status"]),
        "ap_date": col(["APDate", "AP Date"]),
    }
    out = pd.DataFrame()
    for new, old in mapping.items():
        out[new] = df[old] if old else np.nan
    out["source_file"] = source_name
    for c in ["start_date", "end_date", "ap_date"]:
        out[c] = parse_dates(out[c])
    for c in ["days", "native_use", "demand", "common_use", "cost", "prior_balance", "late_fee", "amount_due", "pay_amount"]:
        out[c] = to_num(out[c])
    out["billing_period"] = out["billing_period"].astype(str).str.replace(".0", "", regex=False)
    out["ap_status_norm"] = out["ap_status"].fillna("Blank").astype(str).str.strip().replace({"": "Blank"})
    out["account_key"] = out["account_code"].fillna("").astype(str).str.strip()
    out["meter_key"] = out["meter_code"].fillna("").astype(str).str.strip()
    out["vendor_key"] = out["vendor_code"].fillna("").astype(str).str.strip()
    out["month"] = pd.to_datetime(out["billing_period"].str[:4] + "-" + out["billing_period"].str[4:6] + "-01", errors="coerce")
    return out


def normalize_setup(df: pd.DataFrame) -> pd.DataFrame:
    col = lambda names: coalesce_col(df, names)
    mapping = {
        "account_name": col(["Account Name"]),
        "account_number": col(["Account Number", "Account Code"]),
        "service_dates": col(["Service Dates"]),
        "account_status": col(["Status"]),
        "accruals": col(["Accruals"]),
        "excluded_from_audits": col(["Excluded From Audits (Y/N)", "Excluded From Audits"]),
        "account_address": col(["Account Address"]),
        "account_country": col(["Account Country"]),
        "payment_type": col(["Payment Type"]),
        "delivery_method": col(["Delivery Method"]),
        "bill_frequency": col(["Bill Frequency"]),
        "cost_center_name": col(["Cost Center Name"]),
        "cost_center_code": col(["Cost Center Code"]),
        "vendor_name": col(["Vendor Name"]),
        "vendor_code": col(["Vendor Code"]),
        "vendor_country": col(["Vendor Country"]),
        "rate_schedule": col(["Rate Schedule"]),
        "meter_name": col(["Meter Name"]),
        "meter_code": col(["Meter Code"]),
        "meter_number": col(["Meter Number"]),
        "commodity": col(["Commodity"]),
        "site_name": col(["Site Name"]),
        "site_code": col(["Site Code"]),
        "site_country": col(["Site Country"]),
        "division": col(["Division"]),
        "business_unit": col(["Business Unit"]),
        "master_vendor_code": col(["Master Vendor Code"]),
        "master_account_code": col(["Master Account Code"]),
        "currency_code": col(["Currency Code"]),
        "export_flag": col(["Export Flag"]),
    }
    out = pd.DataFrame()
    for new, old in mapping.items():
        out[new] = df[old] if old else np.nan
    out["account_key"] = out["account_number"].fillna("").astype(str).str.strip()
    out["meter_key"] = out["meter_code"].fillna("").astype(str).str.strip()
    out["vendor_key"] = out["vendor_code"].fillna("").astype(str).str.strip()
    out = out.drop_duplicates(subset=["account_key", "meter_key", "vendor_key"], keep="first")
    return out


def enrich(bills: pd.DataFrame, setup: Optional[pd.DataFrame]) -> pd.DataFrame:
    if setup is None or setup.empty:
        bills["vendor_name"] = bills["vendor_key"]
        bills["site_name"] = bills["place_code"]
        bills["site_code"] = bills["place_code"]
        bills["account_status"] = "Unknown"
        bills["export_flag"] = "Unknown"
        bills["payment_type"] = "Unknown"
        bills["delivery_method"] = "Unknown"
        bills["bill_frequency"] = "Unknown"
        return bills
    # First join on account+meter+vendor. Fallback joins applied afterwards.
    setup_cols = [c for c in setup.columns if c not in []]
    m = bills.merge(setup[setup_cols], on=["account_key", "meter_key", "vendor_key"], how="left", suffixes=("", "_setup"))
    # Fallback by account only for records not matched
    fallback = setup.drop_duplicates(subset=["account_key"], keep="first")
    m2 = bills.merge(fallback.add_suffix("_acct"), left_on="account_key", right_on="account_key_acct", how="left")
    enrich_cols = [c for c in setup.columns if c not in ["account_key", "meter_key", "vendor_key"]]
    for c in enrich_cols:
        if c not in m.columns:
            m[c] = np.nan
        acct_c = c + "_acct"
        if acct_c in m2.columns:
            m[c] = m[c].combine_first(m2[acct_c])
    m["vendor_name"] = m.get("vendor_name", pd.Series(index=m.index, dtype=object)).fillna(m["vendor_key"])
    m["site_name"] = m.get("site_name", pd.Series(index=m.index, dtype=object)).fillna(m["place_code"])
    m["site_code"] = m.get("site_code", pd.Series(index=m.index, dtype=object)).fillna(m["place_code"])
    for c in ["account_status", "export_flag", "payment_type", "delivery_method", "bill_frequency"]:
        if c not in m.columns:
            m[c] = "Unknown"
        m[c] = m[c].fillna("Unknown")
    return m


def calculate_risk(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    d = df.copy()
    today = pd.Timestamp.today().normalize()
    d["has_prior_balance"] = d["prior_balance"].fillna(0) > 0
    d["has_late_fee"] = d["late_fee"].fillna(0) > 0
    d["not_exported_ap"] = d["ap_status_norm"].str.lower().isin(["no", "blank", "nan", "none"])
    d["ap_lag_days"] = (d["ap_date"] - d["end_date"]).dt.days
    d["bill_age_days"] = (today - d["end_date"]).dt.days
    d["unexported_age_days"] = np.where(d["not_exported_ap"], d["bill_age_days"], np.nan)
    d["inactive_but_billed"] = d["account_status"].astype(str).str.lower().ne("active") & d["account_status"].astype(str).str.lower().ne("unknown")
    d["no_export_path"] = d["export_flag"].astype(str).str.upper().isin(["NO", "N", "FALSE", "0"])

    # Account-level aggregation
    group_cols = ["account_key", "vendor_key", "vendor_name", "site_code", "site_name", "commodity_code"]
    acct = d.groupby(group_cols, dropna=False).agg(
        bills=("bill_id", "count"),
        total_cost=("cost", "sum"),
        latest_bill_end=("end_date", "max"),
        latest_month=("month", "max"),
        prior_balance_count=("has_prior_balance", "sum"),
        prior_balance_total=("prior_balance", "sum"),
        late_fee_count=("has_late_fee", "sum"),
        late_fee_total=("late_fee", "sum"),
        not_exported_count=("not_exported_ap", "sum"),
        oldest_unexported_age=("unexported_age_days", "max"),
        avg_ap_lag_days=("ap_lag_days", "mean"),
        max_ap_lag_days=("ap_lag_days", "max"),
        inactive_but_billed=("inactive_but_billed", "max"),
        no_export_path=("no_export_path", "max"),
    ).reset_index()

    # Consecutive prior balance months
    tmp = d.dropna(subset=["month"]).sort_values(["account_key", "month"])
    streaks = []
    for acc, g in tmp.groupby("account_key"):
        cur = maxs = 0
        for val in g.groupby("month")["has_prior_balance"].max().values:
            if val:
                cur += 1
                maxs = max(maxs, cur)
            else:
                cur = 0
        streaks.append((acc, maxs))
    streak_df = pd.DataFrame(streaks, columns=["account_key", "max_consecutive_prior_balance_months"])
    acct = acct.merge(streak_df, on="account_key", how="left")
    acct["max_consecutive_prior_balance_months"] = acct["max_consecutive_prior_balance_months"].fillna(0)

    # Risk score
    acct["risk_score"] = 0
    acct["risk_score"] += np.where(acct["prior_balance_count"] > 0, 25, 0)
    acct["risk_score"] += np.where(acct["max_consecutive_prior_balance_months"] >= 2, 20, 0)
    acct["risk_score"] += np.where(acct["late_fee_count"] > 0, 25, 0)
    acct["risk_score"] += np.where(acct["not_exported_count"] > 0, 10, 0)
    acct["risk_score"] += np.where(acct["oldest_unexported_age"].fillna(0) >= 30, 10, 0)
    acct["risk_score"] += np.where(acct["no_export_path"], 10, 0)
    acct["risk_score"] += np.where(acct["inactive_but_billed"], 10, 0)
    acct["risk_score"] = acct["risk_score"].clip(upper=100)
    acct["risk_level"] = pd.cut(acct["risk_score"], bins=[-1, 24, 49, 74, 100], labels=["Low", "Medium", "High", "Critical"])

    def recommendation(row):
        parts = []
        if row["inactive_but_billed"]:
            parts.append("Validate account/site status; account is not active but has bill activity")
        if row["no_export_path"]:
            parts.append("Verify AP/GL export configuration or alternate payment process")
        if row["prior_balance_count"] > 0 and row["late_fee_count"] > 0:
            parts.append("Escalate with AP and utility; prior balance and late fees indicate payment posting risk")
        elif row["prior_balance_count"] > 0:
            parts.append("Confirm prior balance root cause and whether recent payments posted at the utility")
        elif row["late_fee_count"] > 0:
            parts.append("Review late fee history and tighten payment timing for this account")
        if row["not_exported_count"] > 0:
            parts.append("Review unexported bills and confirm they are queued for AP")
        if not parts:
            parts.append("Monitor; no major AP risk indicators in uploaded data")
        return "; ".join(parts)

    acct["recommended_action"] = acct.apply(recommendation, axis=1)
    acct["priority_rank"] = acct["risk_score"].rank(method="first", ascending=False).astype(int)
    return d, acct.sort_values(["risk_score", "prior_balance_total", "late_fee_total"], ascending=[False, False, False])


def xlsx_download(df: pd.DataFrame, sheet_name="Actions") -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
    return output.getvalue()


def metric(label, value, help=None):
    st.metric(label, value, help=help)

# -------------------------
# UI
# -------------------------

st.title("EnergyCAP AP Risk Dashboard")
st.caption("Late fee, prior-balance, AP export, disconnection-risk, and account-master QA analysis for EnergyCAP exports.")

with st.sidebar:
    st.header("Upload files")
    bill_files = st.file_uploader(
        "Bill Transfer export(s)", type=["xlsx"], accept_multiple_files=True,
        help="Upload one or more Custom ENEL01 Bill Transfer Format Excel exports. 18-24 months is ideal."
    )
    setup_file = st.file_uploader(
        "Optional Report-03 Setup Report", type=["xlsx"], accept_multiple_files=False,
        help="Adds vendor/site/account status, payment type, delivery method, export flag, GL/account mapping, etc."
    )
    st.divider()
    only_active = st.checkbox("Prioritize active accounts only", value=False)
    min_score = st.slider("Minimum risk score in action list", 0, 100, 25)

if not bill_files:
    st.info("Upload at least one EnergyCAP Bill Transfer export to begin. Add Report-03 for richer recommendations.")
    st.stop()

try:
    bill_frames = []
    for f in bill_files:
        raw = read_energycap_excel(f, "bill")
        bill_frames.append(normalize_bill(raw, f.name))
    bills = pd.concat(bill_frames, ignore_index=True)

    setup = None
    if setup_file is not None:
        setup_raw = read_energycap_excel(setup_file, "setup")
        setup = normalize_setup(setup_raw)

    data = enrich(bills, setup)
    data, account_risk = calculate_risk(data)
except Exception as e:
    st.error("The app could not parse the uploaded file(s). Confirm they are EnergyCAP Excel exports and not password-protected.")
    st.exception(e)
    st.stop()

if only_active and "account_status" in account_risk.columns:
    active_keys = data.loc[data["account_status"].astype(str).str.lower().eq("active"), "account_key"].unique()
    account_risk = account_risk[account_risk["account_key"].isin(active_keys)]
    data = data[data["account_key"].isin(active_keys)]

tabs = st.tabs([
    "Summary", "AP Processing", "Prior Balance & Late Fees", "Vendor / Site Risk", "Account Master QA", "Recommended Actions", "Raw Data"
])

with tabs[0]:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Bills", f"{len(data):,}")
    c2.metric("Spend", f"${data['cost'].fillna(0).sum():,.0f}")
    c3.metric("Late fees", f"${data['late_fee'].fillna(0).sum():,.0f}")
    c4.metric("Accounts w/ prior balance", f"{account_risk.loc[account_risk['prior_balance_count']>0,'account_key'].nunique():,}")
    c5.metric("Critical / High accounts", f"{account_risk[account_risk['risk_level'].isin(['Critical','High'])].shape[0]:,}")

    left, right = st.columns([1.2, 1])
    with left:
        st.subheader("Monthly risk indicators")
        trend = data.dropna(subset=["month"]).groupby("month").agg(
            spend=("cost", "sum"), prior_balance=("prior_balance", "sum"), late_fee=("late_fee", "sum"), unexported=("not_exported_ap", "sum")
        ).reset_index()
        if not trend.empty:
            fig = px.line(trend, x="month", y=["prior_balance", "late_fee"], markers=True, title="Prior balance and late fees by billing month")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("No valid billing periods were found for trend analysis.")
    with right:
        st.subheader("Top risk accounts")
        st.dataframe(account_risk.head(10)[["risk_level", "risk_score", "account_key", "vendor_name", "site_name", "commodity_code", "recommended_action"]], use_container_width=True, hide_index=True)

with tabs[1]:
    st.subheader("AP processing analysis")
    c1, c2, c3 = st.columns(3)
    c1.metric("Not exported to AP", f"{int(data['not_exported_ap'].sum()):,}")
    c2.metric("Avg AP lag days", f"{data['ap_lag_days'].dropna().mean():.1f}" if data['ap_lag_days'].notna().any() else "n/a")
    c3.metric("Oldest unexported bill age", f"{data['unexported_age_days'].dropna().max():.0f} days" if data['unexported_age_days'].notna().any() else "n/a")
    col1, col2 = st.columns(2)
    with col1:
        status = data.groupby("ap_status_norm").size().reset_index(name="bills")
        st.plotly_chart(px.bar(status, x="ap_status_norm", y="bills", title="AP status breakdown"), use_container_width=True)
    with col2:
        vendor_lag = data.groupby("vendor_name").agg(avg_ap_lag=("ap_lag_days", "mean"), bills=("bill_id", "count"), not_exported=("not_exported_ap", "sum")).reset_index().sort_values("not_exported", ascending=False).head(20)
        st.plotly_chart(px.bar(vendor_lag, x="vendor_name", y="not_exported", title="Unexported bills by vendor"), use_container_width=True)
    st.subheader("Oldest / highest-value unexported bills")
    unexp = data[data["not_exported_ap"]].sort_values(["unexported_age_days", "cost"], ascending=[False, False])
    st.dataframe(unexp[["account_key", "vendor_name", "site_name", "commodity_code", "end_date", "cost", "amount_due", "ap_status_norm", "unexported_age_days", "source_file"]].head(100), use_container_width=True, hide_index=True)

with tabs[2]:
    st.subheader("Prior balance & late fee analysis")
    col1, col2 = st.columns(2)
    with col1:
        pb = account_risk[account_risk["prior_balance_count"] > 0].head(25)
        st.dataframe(pb[["risk_level", "risk_score", "account_key", "vendor_name", "site_name", "prior_balance_count", "prior_balance_total", "max_consecutive_prior_balance_months", "recommended_action"]], use_container_width=True, hide_index=True)
    with col2:
        lf = account_risk[account_risk["late_fee_count"] > 0].sort_values("late_fee_total", ascending=False).head(25)
        st.dataframe(lf[["risk_level", "risk_score", "account_key", "vendor_name", "site_name", "late_fee_count", "late_fee_total", "recommended_action"]], use_container_width=True, hide_index=True)
    monthly = data.dropna(subset=["month"]).groupby(["month", "vendor_name"]).agg(prior_balance=("prior_balance", "sum"), late_fee=("late_fee", "sum")).reset_index()
    if not monthly.empty:
        st.plotly_chart(px.area(monthly, x="month", y="prior_balance", color="vendor_name", title="Prior balance by vendor over time"), use_container_width=True)

with tabs[3]:
    st.subheader("Vendor / site risk scorecards")
    v = account_risk.groupby("vendor_name").agg(accounts=("account_key", "nunique"), avg_risk=("risk_score", "mean"), critical_high=("risk_level", lambda s: s.isin(["Critical", "High"]).sum()), prior_balance=("prior_balance_total", "sum"), late_fees=("late_fee_total", "sum"), unexported=("not_exported_count", "sum")).reset_index().sort_values(["critical_high", "avg_risk"], ascending=False)
    s = account_risk.groupby("site_name").agg(accounts=("account_key", "nunique"), avg_risk=("risk_score", "mean"), critical_high=("risk_level", lambda x: x.isin(["Critical", "High"]).sum()), prior_balance=("prior_balance_total", "sum"), late_fees=("late_fee_total", "sum"), unexported=("not_exported_count", "sum")).reset_index().sort_values(["critical_high", "avg_risk"], ascending=False)
    col1, col2 = st.columns(2)
    with col1:
        st.dataframe(v.head(30), use_container_width=True, hide_index=True)
        st.plotly_chart(px.bar(v.head(15), x="vendor_name", y="critical_high", title="Critical/high-risk accounts by vendor"), use_container_width=True)
    with col2:
        st.dataframe(s.head(30), use_container_width=True, hide_index=True)
        st.plotly_chart(px.bar(s.head(15), x="site_name", y="critical_high", title="Critical/high-risk accounts by site"), use_container_width=True)

with tabs[4]:
    st.subheader("Account master QA")
    if setup is None:
        st.info("Upload Report-03 to enable account master QA checks.")
    else:
        qa = data.copy()
        qa["missing_vendor_name"] = qa["vendor_name"].isna() | qa["vendor_name"].astype(str).str.lower().isin(["", "nan", "unknown"])
        qa["missing_site"] = qa["site_name"].isna() | qa["site_name"].astype(str).str.lower().isin(["", "nan", "unknown"])
        qa["missing_export_flag"] = qa["export_flag"].isna() | qa["export_flag"].astype(str).str.lower().isin(["", "nan", "unknown"])
        qa_acct = qa.groupby(["account_key", "vendor_name", "site_name", "commodity_code"], dropna=False).agg(
            bills=("bill_id", "count"), inactive_but_billed=("inactive_but_billed", "max"), no_export_path=("no_export_path", "max"), missing_export_flag=("missing_export_flag", "max"), payment_type=("payment_type", "first"), delivery_method=("delivery_method", "first"), bill_frequency=("bill_frequency", "first"), export_flag=("export_flag", "first"), account_status=("account_status", "first")
        ).reset_index()
        c1, c2, c3 = st.columns(3)
        c1.metric("Inactive but billed", f"{qa_acct['inactive_but_billed'].sum():,}")
        c2.metric("No AP/GL export path", f"{qa_acct['no_export_path'].sum():,}")
        c3.metric("Missing/unknown export flag", f"{qa_acct['missing_export_flag'].sum():,}")
        st.dataframe(qa_acct[(qa_acct["inactive_but_billed"] | qa_acct["no_export_path"] | qa_acct["missing_export_flag"])].head(200), use_container_width=True, hide_index=True)

with tabs[5]:
    st.subheader("Recommended / prioritized actions")
    actions = account_risk[account_risk["risk_score"] >= min_score].copy()
    actions = actions.sort_values(["risk_score", "prior_balance_total", "late_fee_total", "not_exported_count"], ascending=False)
    display_cols = ["risk_level", "risk_score", "priority_rank", "account_key", "vendor_name", "site_name", "commodity_code", "bills", "prior_balance_count", "prior_balance_total", "late_fee_count", "late_fee_total", "not_exported_count", "oldest_unexported_age", "max_consecutive_prior_balance_months", "recommended_action"]
    st.dataframe(actions[display_cols], use_container_width=True, hide_index=True)
    st.download_button("Download action register (Excel)", data=xlsx_download(actions[display_cols + [c for c in actions.columns if c not in display_cols]]), file_name="energycap_ap_risk_action_register.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

with tabs[6]:
    st.subheader("Normalized bill data")
    st.dataframe(data, use_container_width=True, hide_index=True)
    st.download_button("Download normalized data (CSV)", data=data.to_csv(index=False).encode("utf-8"), file_name="normalized_energycap_bill_data.csv", mime="text/csv")
