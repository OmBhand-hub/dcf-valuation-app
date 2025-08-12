import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import yfinance as yf

# ------------------ Helpers (tiny, readable) ------------------
def _find_row_case_insensitive(df, candidates):
    """Return the row (Series) from df where index matches any name in candidates (case-insensitive)."""
    if df is None or df.empty:
        return None
    idx = {str(i).strip().lower(): i for i in df.index}
    for cand in candidates:
        key = cand.strip().lower()
        if key in idx:
            return df.loc[idx[key]]
    return None

def _latest_value(series):
    """Return the most recent (left-most) non-null value from a Yahoo statement row."""
    if series is None:
        return None
    try:
        return float(series.dropna().iloc[0])  # newest period is column 0 in yfinance
    except Exception:
        return None

def _get_current_price(stock: yf.Ticker):
    """Try fast_info → info → last close. Keep it simple and robust."""
    try:
        fi = getattr(stock, "fast_info", None)
        if fi:
            for k in ("last_price", "lastPrice", "last"):
                if k in fi and fi[k]:
                    return float(fi[k])
    except Exception:
        pass
    try:
        price = stock.info.get("currentPrice", None)
        if price:
            return float(price)
    except Exception:
        pass
    try:
        hist = stock.history(period="1d")
        if hist is not None and not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    return None

# ------------------ App UI ------------------
st.set_page_config(page_title="DCF Valuation App", layout="centered")
st.title("📊 DCF Valuation App")

# Simple explainer so you can describe the app clearly
with st.expander("How this app works (read me)"):
    st.markdown(
        """
**What it does:**  
- Pulls basic financials with yfinance.  
- Estimates intrinsic value using a simple DCF (project FCF → discount → add terminal value).  
- Compares implied share price vs current market price.  
- Flags undervalued / overvalued using your Margin of Safety.

**Key inputs (and meaning):**  
- **FCF (auto)**: last reported free cash flow (or OCF − CapEx if FCF line missing).  
- **WACC (auto)**: a quick mix of cost of equity and after-tax cost of debt from current cap structure.  
- **Growth %**: expected annual FCF growth during the projection window.  
- **Terminal growth %**: long-run growth after the projection (used in Gordon Growth).  
- **Margin of Safety %**: your required discount vs market before calling something “undervalued”.

**Core formulas (high level):**  
- Discounted FCF\_t = FCF\_t / (1 + WACC)^t  
- Terminal Value = FCF\_last × (1 + g) / (WACC − g)  
- Intrinsic Equity (per share) ≈ DCF total / Shares Outstanding  
- Valuation flag: compare implied price to market with your MOS threshold.
        """
    )

st.subheader("Enter Stock Ticker to Auto-Fill Financials")
ticker = st.text_input("Enter stock ticker (e.g., AAPL, MSFT, TSLA)", value="AAPL")

# Sidebar: keep investor preferences here (cleaner main pane)
st.sidebar.header("Investor Settings")
mos_percent = st.sidebar.slider("Margin of Safety Threshold (%)", min_value=0, max_value=50, value=25, step=1)
tax_rate = st.sidebar.number_input("Corporate Tax Rate (%)", min_value=0.0, max_value=100.0, value=21.0, step=0.1)

# Working variables
fcf = 0.0
equity_value = 0.0
debt_value = 0.0
current_price = None

# ------------------ Data fetch ------------------
if ticker:
    try:
        stock = yf.Ticker(ticker)

        # Equity value (market cap) for WACC weights
        try:
            equity_value = float(stock.info.get("marketCap", 0.0) or 0.0)
        except Exception:
            equity_value = 0.0

        # Current market price for comparison
        current_price = _get_current_price(stock)

        # Debt: try "Total Debt", else sum common components
        try:
            balance_sheet = stock.balance_sheet  # annual; newest column first
            if balance_sheet is not None and not balance_sheet.empty:
                total_debt_direct = _find_row_case_insensitive(balance_sheet, ["Total Debt"])
                long_term_debt     = _find_row_case_insensitive(balance_sheet, ["Long Term Debt", "Long-Term Debt"])
                current_portion_lt = _find_row_case_insensitive(balance_sheet, ["Short Long Term Debt", "Current Portion Of Long Term Debt"])
                short_term_debt    = _find_row_case_insensitive(balance_sheet, ["Short Term Debt", "Short-Term Debt"])

                if total_debt_direct is not None:
                    debt_value = _latest_value(total_debt_direct) or 0.0
                else:
                    parts = [s for s in [long_term_debt, current_portion_lt, short_term_debt] if s is not None]
                    if parts:
                        debt_value = float(pd.concat(parts, axis=1).fillna(0.0).sum(axis=1).dropna().iloc[0])
                    else:
                        # Soft fallback: liabilities (not ideal, but avoids always-zero)
                        total_liab = _find_row_case_insensitive(
                            balance_sheet,
                            ["Total Liab", "Total Liabilities", "Total Liabilities Net Minority Interest"]
                        )
                        debt_value = _latest_value(total_liab) or 0.0
            else:
                debt_value = 0.0

            debt_value = float(debt_value or 0.0)
        except Exception as e:
            st.warning(f"⚠️ Couldn't extract debt: {e}")
            debt_value = 0.0

        # FCF: use Yahoo "Free Cash Flow" if present, else OCF − CapEx
        try:
            cashflow = stock.cashflow
            if cashflow is not None and not cashflow.empty:
                if "Free Cash Flow" in cashflow.index:
                    fcf = float(cashflow.loc["Free Cash Flow"].dropna().iloc[0])
                elif (
                    "Total Cash From Operating Activities" in cashflow.index
                    and "Capital Expenditures" in cashflow.index
                ):
                    op_cf = float(cashflow.loc["Total Cash From Operating Activities"].dropna().iloc[0])
                    capex = float(cashflow.loc["Capital Expenditures"].dropna().iloc[0])
                    fcf = op_cf - capex
        except Exception as e:
            st.warning(f"⚠️ Couldn't extract FCF: {e}")

        # Defaults to keep everything numeric
        fcf = float(fcf or 0.0)
        equity_value = float(equity_value or 0.0)
        debt_value = float(debt_value or 0.0)

        # Quick confirmation
        st.success(
            f"Fetched values for {ticker.upper()}: "
            f"FCF = ${fcf/1e6:.1f}M, Equity = ${equity_value:,.0f}, Debt = ${debt_value:,.0f}"
        )

        # Optional: inspect what Yahoo calls the rows (helps you explain)
        with st.expander("Balance sheet rows (debug)"):
            try:
                st.write(list(map(str, balance_sheet.index)))
            except Exception:
                st.write("No balance sheet available.")

    except Exception as e:
        st.error(f"❌ Failed to fetch data for {ticker.upper()}. Reason: {e}")
        fcf = equity_value = debt_value = 0.0
        current_price = None

st.markdown("Estimate the intrinsic value of a company using a Discounted Cash Flow (DCF) model.")

# ------------------ WACC (lightweight) ------------------
total_value = equity_value + debt_value
if total_value > 0:
    cost_of_equity = 10.0  # simple default (%)
    cost_of_debt = 5.0     # simple default (%)
    wacc = ((equity_value / total_value) * (cost_of_equity / 100.0)) + \
           ((debt_value / total_value) * (cost_of_debt / 100.0) * (1 - tax_rate / 100.0))
    st.success(f"✅ Calculated WACC: {wacc:.2%}")
else:
    wacc = 0.0
    st.warning("⚠️ Enter valid equity and debt values to calculate WACC.")

# ------------------ DCF Inputs ------------------
st.markdown("---")
st.subheader("Step 2: DCF Inputs")

growth_rate = st.number_input("Expected annual growth rate (%)", min_value=0.0, value=5.0, step=0.5)
discount_rate = wacc  # keep as decimal
st.markdown(f"**Calculated WACC as Discount Rate:** {wacc*100:.2f}%")
years = st.slider("Number of years to project", min_value=1, max_value=10, value=5)
terminal_growth = st.number_input("Terminal growth rate (%)", min_value=0.0, value=2.0, step=0.5)

# ------------------ DCF Calculation (transparent) ------------------
fcf_list = []
for i in range(1, years + 1):
    future_fcf = fcf * (1 + growth_rate / 100.0) ** i
    discounted_fcf = future_fcf / ((1 + discount_rate) ** i)  # discount_rate is decimal
    fcf_list.append(discounted_fcf)

# Terminal value (Gordon Growth)
last_fcf = fcf * (1 + growth_rate / 100.0) ** years
try:
    terminal_value = (last_fcf * (1 + terminal_growth / 100.0)) / (discount_rate - terminal_growth / 100.0)
except Exception:
    terminal_value = 0.0
discounted_terminal = terminal_value / ((1 + discount_rate) ** years)

dcf_value = sum(fcf_list) + discounted_terminal  # currency units
st.subheader(f"💰 Estimated Intrinsic Value: **${dcf_value/1e6:,.2f} million**")

# ------------------ Implied Share Price + Valuation Flag ------------------
shares_outstanding = 0
try:
    shares_outstanding = int(stock.info.get("sharesOutstanding", 0) or 0)
except Exception:
    shares_outstanding = 0

if shares_outstanding > 0:
    implied_price = dcf_value / shares_outstanding  # dcf_value in currency units
    mos_threshold = mos_percent / 100.0

    cols = st.columns(4)
    with cols[0]:
        st.metric("Current Price", f"${(current_price or 0):,.2f}")
    with cols[1]:
        st.metric("Implied Price (DCF)", f"${implied_price:,.2f}")
    with cols[2]:
        if current_price:
            gap = implied_price - current_price
            gap_pct = gap / current_price
            st.metric("Upside vs Market", f"{gap_pct*100:,.1f}%")
        else:
            st.metric("Upside vs Market", "N/A")
    with cols[3]:
        st.metric("Margin of Safety", f"{mos_percent}%")

    # Label using your MOS: undervalued if implied >= price*(1+MOS); overvalued if implied <= price*(1−MOS)
    if current_price:
        upper = current_price * (1 + mos_threshold)
        lower = current_price * (1 - mos_threshold)
        if implied_price >= upper:
            st.success(f"✅ **Undervalued** by ≥ {mos_percent}% vs market price.")
        elif implied_price <= lower:
            st.error(f"❌ **Overvalued** by ≥ {mos_percent}% vs market price.")
        else:
            st.info(f"ℹ️ **Around fair value** (within ±{mos_percent}%).")
else:
    st.warning("⚠️ Could not fetch shares outstanding to calculate implied share price.")

# ------------------ Charts (simple and explainable) ------------------
years_range = list(range(1, years + 1))
future_fcf_list = [fcf * (1 + growth_rate / 100.0) ** i for i in years_range]

st.subheader("📈 Projected Free Cash Flows")
fcf_df = pd.DataFrame({'Year': years_range, 'Future FCF': future_fcf_list})
st.line_chart(fcf_df.set_index("Year"))

st.subheader("💰 Intrinsic Value Breakdown")
labels = ['Discounted FCF', 'Discounted Terminal Value']
values = [sum(fcf_list), discounted_terminal]

if all(v > 0 for v in values):
    fig, ax = plt.subplots()
    ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=90)
    ax.axis('equal')
    st.pyplot(fig)
else:
    st.warning("⚠️ Unable to display pie chart: Values must be positive.")

# ------------------ Sensitivity Table (kept simple) ------------------
st.subheader("📊 Sensitivity Analysis")

discount_rates = [0.08, 0.09, 0.10, 0.11, 0.12]  # decimals
growth_rates = [0.01, 0.02, 0.03, 0.04, 0.05]

table = []
for g in growth_rates:
    row = []
    for r in discount_rates:
        intrinsic = 0.0
        for i in range(years):
            intrinsic += fcf / ((1 + r) ** (i + 1))  # constant FCF stream for illustration
        try:
            terminal = (fcf * (1 + g)) / (r - g)
        except Exception:
            terminal = 0.0
        terminal /= (1 + r) ** years
        total_val = intrinsic + terminal
        row.append(round(total_val / 1e6, 2))  # show in millions
    table.append(row)

df_table = pd.DataFrame(
    table,
    index=[f"{int(g*100)}%" for g in growth_rates],
    columns=[f"{int(r*100)}%" for r in discount_rates]
)
st.dataframe(df_table.style.format("{:.2f}"), height=250)

st.markdown("© 2025 Om Bhand. All rights reserved.", unsafe_allow_html=True)

