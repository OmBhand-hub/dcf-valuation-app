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

def money_short(x):
    """Format currency with M/B suffix (2 dp). e.g., $1.23B, $456.78M, $12,345.67"""
    if x is None:
        return "N/A"
    try:
        x = float(x)
    except Exception:
        return "N/A"
    ax = abs(x)
    if ax >= 1e9:
        return f"${x/1e9:,.2f}B"
    elif ax >= 1e6:
        return f"${x/1e6:,.2f}M"
    else:
        return f"${x:,.2f}"

def money(x):
    """Plain currency with commas and 2 dp. e.g., $123.45"""
    if x is None:
        return "N/A"
    try:
        return f"${float(x):,.2f}"
    except Exception:
        return "N/A"

def valuation_badge(label: str, color: str):
    """Render a bold colored badge."""
    st.markdown(
        f"""
        <div style="
            display:inline-block;
            padding:10px 16px;
            border-radius:12px;
            background:{color};
            color:white;
            font-weight:700;
            font-size:16px;
            ">
            {label}
        </div>
        """,
        unsafe_allow_html=True
    )

# ------------------ App UI ------------------
st.set_page_config(page_title="DCF Valuation App", layout="centered")
st.title("📊 DCF Valuation App")

# Sidebar: preferences (and a toggle to hide/show explainer)
st.sidebar.header("Investor Settings")
show_explainer = st.sidebar.checkbox("Show explainer", value=True)
mos_percent = st.sidebar.slider("Margin of Safety Threshold (%)", min_value=0, max_value=50, value=25, step=1)
tax_rate = st.sidebar.number_input("Corporate Tax Rate (%)", min_value=0.0, max_value=100.0, value=21.0, step=0.1)

# Always-visible explainer (toggleable)
if show_explainer:
    st.markdown(
        """
### How this app works
**What it does:**  
• Pulls basic financials with yfinance.  
• Estimates intrinsic value using a simple DCF (project FCF → discount → terminal value).  
• Compares implied share price vs current market price.  
• Flags undervalued / overvalued using your Margin of Safety.

**Key inputs (plain English):**  
• **FCF (auto):** last reported free cash flow (or OCF − CapEx if FCF line missing).  
• **WACC (auto):** quick mix of cost of equity and after-tax cost of debt from current cap structure.  
• **Growth %:** expected annual FCF growth during the projection window.  
• **Terminal growth %:** long-run growth after the projection (Gordon Growth).  
• **Margin of Safety %:** your required discount vs market before calling it “undervalued”.

**Core formulas:**  
• Discounted FCFₜ = FCFₜ / (1 + WACC)ᵗ  
• Terminal Value = FCF_last × (1 + g) / (WACC − g)  
• Implied Price = (DCF total value) / Shares Outstanding  
• Label: compare implied price to market using your MOS threshold.
"""
    )

st.markdown("---")

st.subheader("Step 1: Pull the company’s key financials")
ticker = st.text_input("Enter stock ticker (e.g., AAPL, MSFT, TSLA)", value="AAPL")

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

        # Quick confirmation (formatted with M/B suffixes)
        st.success(
            f"Fetched values for {ticker.upper()}: "
            f"FCF = {money_short(fcf)}, Equity = {money_short(equity_value)}, Debt = {money_short(debt_value)}"
        )

        # Optional: inspect Yahoo row names
        with st.expander("Balance sheet rows (debug)"):
            try:
                st.write(list(map(str, balance_sheet.index)))
            except Exception:
                st.write("No balance sheet available.")

    except Exception as e:
        st.error(f"❌ Failed to fetch data for {ticker.upper()}. Reason: {e}")
        fcf = equity_value = debt_value = 0.0
        current_price = None

st.markdown("---")

# ------------------ WACC (lightweight) ------------------
st.subheader("Step 2: Estimate the discount rate (WACC)")
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

st.markdown("---")

# ------------------ DCF Inputs ------------------
st.subheader("Step 3: Project the company’s future cash flows")
growth_rate = st.number_input("Expected annual growth rate (%)", min_value=0.0, value=5.0, step=0.5)
discount_rate = wacc  # keep as decimal
st.markdown(f"**Using WACC as Discount Rate:** {wacc*100:.2f}%")
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

st.markdown("---")

# ------------------ Implied Price + Decision ------------------
st.subheader("Step 4: Value the business and compare with market")

st.metric("Estimated Intrinsic Value (DCF)", money_short(dcf_value))

shares_outstanding = 0
try:
    shares_outstanding = int(stock.info.get("sharesOutstanding", 0) or 0)
except Exception:
    shares_outstanding = 0

if shares_outstanding > 0:
    implied_price = dcf_value / shares_outstanding  # per share
    mos_threshold = mos_percent / 100.0

    cols = st.columns(4)
    with cols[0]:
        st.metric("Current Price", money(current_price or 0))
    with cols[1]:
        st.metric("Implied Price (DCF)", money(implied_price))
    with cols[2]:
        if current_price:
            gap_pct = (implied_price - current_price) / current_price
            st.metric("Upside vs Market", f"{gap_pct*100:,.1f}%")
        else:
            st.metric("Upside vs Market", "N/A")
    with cols[3]:
        st.metric("Margin of Safety", f"{mos_percent}%")

    # Badge using MOS threshold
    if current_price:
        upper = current_price * (1 + mos_threshold)
        lower = current_price * (1 - mos_threshold)
        if implied_price >= upper:
            valuation_badge("UNDERVALUED", "#16a34a")  # green-600
        elif implied_price <= lower:
            valuation_badge("OVERVALUED", "#dc2626")   # red-600
        else:
            valuation_badge("AROUND FAIR VALUE", "#6b7280")  # gray-500
else:
    st.warning("⚠️ Could not fetch shares outstanding to calculate implied share price.")

st.markdown("---")

# ------------------ Charts (simple and explainable) ------------------
st.subheader("Visualise the projection")
years_range = list(range(1, years + 1))
future_fcf_list = [fcf * (1 + growth_rate / 100.0) ** i for i in years_range]

st.markdown("**Projected Free Cash Flows**")
fcf_df = pd.DataFrame({'Year': years_range, 'Future FCF': future_fcf_list})
st.line_chart(fcf_df.set_index("Year"))

st.markdown("**Intrinsic Value Breakdown**")
labels = ['Discounted FCF', 'Discounted Terminal Value']
values = [sum(fcf_list), discounted_terminal]

if all(v > 0 for v in values):
    fig, ax = plt.subplots()
    ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=90)
    ax.axis('equal')
    st.pyplot(fig)
else:
    st.warning("⚠️ Unable to display pie chart: values must be positive.")

st.markdown("---")

# ------------------ Sensitivity Table (kept simple) ------------------
st.subheader("Sensitivity: constant FCF toy model (millions)")
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
        row.append(round(total_val / 1e6, 2))  # show in millions with 2 dp
    table.append(row)

df_table = pd.DataFrame(
    table,
    index=[f"{int(g*100)}%" for g in growth_rates],
    columns=[f"{int(r*100)}%" for r in discount_rates]
)
st.dataframe(df_table.style.format("{:.2f}"), height=250)

st.markdown("---")
st.caption("This tool is for educational purposes and does not constitute investment advice.")
st.markdown("© 2025 Om Bhand. All rights reserved.", unsafe_allow_html=True)
