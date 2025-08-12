import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import yfinance as yf
import html  # for safe escaping in the custom panel

# ----------------------------
# Helpers
# ----------------------------
def money_short(x):
    """Format number with $ and M/B/T suffix, 2 dp, with commas."""
    if x is None:
        return "N/A"
    try:
        x = float(x)
    except Exception:
        return "N/A"
    ax = abs(x)
    if ax >= 1e12:   # Trillions
        return f"${x/1e12:,.2f}T"
    if ax >= 1e9:    # Billions
        return f"${x/1e9:,.2f}B"
    if ax >= 1e6:    # Millions
        return f"${x/1e6:,.2f}M"
    return f"${x:,.2f}"

def money(x):
    """Plain $ with commas and 2 dp."""
    if x is None:
        return "N/A"
    try:
        return f"${float(x):,.2f}"
    except Exception:
        return "N/A"

def green_panel(title: str, lines: list[str]):
    """Clean, consistent green box (no markdown quirks)."""
    safe_title = html.escape(title)
    safe_lines = [html.escape(line) for line in lines]
    st.markdown(
        f"""
        <div style="
            background:#143D2A;
            border:1px solid #14532d;
            border-radius:12px;
            padding:16px;">
            <div style="font-weight:600; margin-bottom:6px;">{safe_title}</div>
            <div style="line-height:1.6;">
                {"<br>".join(safe_lines)}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

# ----------------------------
# Streamlit Page Config
# ----------------------------
st.set_page_config(page_title="DCF Valuation App", layout="centered")
st.title("📊 DCF Valuation App")

# Intro / How it works (unchanged)
st.markdown("""
### How it works
This app estimates a company's intrinsic value using a Discounted Cash Flow (DCF) model.
We now discount **Free Cash Flow to Equity (FCFE)** at the **Cost of Equity** and use a **3-year average FCFE** to stabilize inputs.

**Steps:**
1) Fetch Free Cash Flow, Market Cap (Equity), and Debt from Yahoo Finance  
2) Set discount rate (Cost of Equity)  
3) Project and discount future cash flows + terminal value  
4) Compare implied price vs market with your Margin of Safety
""")

# ----------------------------
# Step 1: Fetch financial data
# ----------------------------
st.markdown("---")
st.subheader("Step 1: Fetch the company's financials")

ticker = st.text_input("Enter stock ticker (e.g., AAPL, MSFT, TSLA)", value="AAPL")

# working vars
equity_value = 0.0
debt_value = 0.0
fcfe_latest = 0.0
fcfe_avg3 = 0.0

if ticker:
    try:
        stock = yf.Ticker(ticker)

        # --- EQUITY VALUE (Market Cap) ---
        equity_value = float(stock.info.get("marketCap", 0) or 0)

        # --- DEBT VALUE (robust: annual + quarterly, flexible labels) ---
        try:
            debt_value = 0.0
            bs_sources = [stock.balance_sheet, stock.quarterly_balance_sheet]
            for bs in bs_sources:
                if bs is not None and not bs.empty:
                    matches = [idx for idx in bs.index
                               if ("total liab" in str(idx).lower()) or ("total liabilities" in str(idx).lower())]
                    if matches:
                        debt_value = float(pd.Series(bs.loc[matches[0]]).dropna().iloc[0])
                        break
        except Exception as e:
            st.warning(f"⚠️ Couldn't extract debt: {e}")
            debt_value = 0.0

        # --- FCFE: use Yahoo "Free Cash Flow" (CFO - CapEx), compute 3-year average ---
        fcfe_series = None
        try:
            cf = stock.cashflow  # annual; columns newest->oldest
            if cf is not None and not cf.empty:
                if "Free Cash Flow" in cf.index:
                    fcfe_series = pd.Series(cf.loc["Free Cash Flow"]).dropna()
                elif ("Total Cash From Operating Activities" in cf.index) and ("Capital Expenditures" in cf.index):
                    op = pd.Series(cf.loc["Total Cash From Operating Activities"]).fillna(0)
                    capex = pd.Series(cf.loc["Capital Expenditures"]).fillna(0)
                    fcfe_series = (op - capex).dropna()
        except Exception as e:
            st.warning(f"⚠️ Couldn't extract FCFE: {e}")

        if fcfe_series is not None and not fcfe_series.empty:
            fcfe_latest = float(fcfe_series.iloc[0])
            fcfe_avg3 = float(fcfe_series.iloc[:3].mean()) if len(fcfe_series) >= 1 else float(fcfe_series.iloc[0])
        else:
            fcfe_latest = 0.0
            fcfe_avg3 = 0.0

        # --- Clean fetched-values panel ---
        green_panel(
            f"Fetched values for {ticker.upper()}:",
            [
                f"Free Cash Flow to Equity (latest): {money_short(fcfe_latest)}",
                f"Free Cash Flow to Equity (3-yr avg): {money_short(fcfe_avg3)}",
                f"Equity Value (Market Cap): {money_short(equity_value)}",
                f"Debt (Total Liabilities proxy if needed): {money_short(debt_value)}",
            ],
        )

    except Exception as e:
        st.error(f"❌ Failed to fetch data for {ticker.upper()}. Reason: {e}")
        equity_value = debt_value = fcfe_latest = fcfe_avg3 = 0.0

# ----------------------------
# Step 2: Discount rate (Cost of Equity)
# ----------------------------
st.markdown("---")
st.subheader("Step 2: Set the discount rate (Cost of Equity)")

# Keep your original fixed assumption so it's explainable
cost_of_equity_pct = st.number_input("Cost of Equity (%)", min_value=0.0, max_value=30.0, value=10.0, step=0.5)
ke = cost_of_equity_pct / 100.0  # decimal
st.info(f"Using Cost of Equity: **{cost_of_equity_pct:.2f}%**")

# ----------------------------
# Step 3: Project the company's future cash flows (FCFE)
# ----------------------------
st.markdown("---")
st.subheader("Step 3: Project the company’s future cash flows (FCFE)")

growth_rate = st.number_input("Expected annual growth rate (%)", min_value=0.0, value=6.0, step=0.5)
years = st.slider("Number of years to project", min_value=1, max_value=10, value=5)
terminal_growth = st.number_input("Terminal growth rate (%)", min_value=0.0, value=2.0, step=0.5)

base_fcfe = fcfe_avg3  # stabilized starting point

# DCF on FCFE discounted at Cost of Equity
fcfe_pvs = []
for i in range(1, years + 1):
    future_fcfe = base_fcfe * (1 + growth_rate / 100.0) ** i
    pv_fcfe = future_fcfe / ((1 + ke) ** i)
    fcfe_pvs.append(pv_fcfe)

last_fcfe = base_fcfe * (1 + growth_rate / 100.0) ** years
try:
    terminal_equity_value = (last_fcfe * (1 + terminal_growth / 100.0)) / (ke - terminal_growth / 100.0)
    terminal_equity_pv = terminal_equity_value / ((1 + ke) ** years)
except Exception:
    terminal_equity_pv = 0.0

intrinsic_equity_value = sum(fcfe_pvs) + terminal_equity_pv  # this is TOTAL equity value ($)

st.subheader("Estimated Intrinsic Value (DCF)")
st.metric("Intrinsic Equity Value", money_short(intrinsic_equity_value))

# ----------------------------
# Step 4: Compare to market price
# ----------------------------
st.markdown("---")
st.subheader("Step 4: Compare to market price")

# Shares outstanding and current price
shares_outstanding = 0
current_price = None
try:
    shares_outstanding = int(yf.Ticker(ticker).info.get("sharesOutstanding", 0) or 0)
except Exception:
    shares_outstanding = 0
try:
    current_price = float(yf.Ticker(ticker).history(period="1d")["Close"].iloc[-1])
except Exception:
    current_price = None

if shares_outstanding > 0:
    implied_price = intrinsic_equity_value / shares_outstanding  # per-share equity value
    mos = st.slider("Margin of Safety (%)", min_value=0, max_value=50, value=20, step=5)
    target_price = implied_price * (1 - mos / 100.0)

    # Badge / label
    if current_price is not None:
        if current_price < target_price:
            st.markdown("<span style='color:green; font-weight:bold; font-size:18px;'>✅ Undervalued</span>", unsafe_allow_html=True)
        elif current_price > implied_price:
            st.markdown("<span style='color:red; font-weight:bold; font-size:18px;'>❌ Overvalued</span>", unsafe_allow_html=True)
        else:
            st.markdown("<span style='color:orange; font-weight:bold; font-size:18px;'>⚖️ Fairly Valued</span>", unsafe_allow_html=True)

    cols = st.columns(3)
    with cols[0]:
        st.metric("Implied Price (DCF)", money(implied_price))
    with cols[1]:
        st.metric("Current Price", money(current_price))
    with cols[2]:
        st.metric(f"Target Buy (MOS {mos}%)", money(target_price))
else:
    st.warning("⚠️ Could not fetch shares outstanding to calculate implied share price.")

# ----------------------------
# Step 5: Charts
# ----------------------------
st.markdown("---")
st.subheader("📈 Projected Free Cash Flows (FCFE)")

years_range = list(range(1, years + 1))
future_fcfe_list = [base_fcfe * (1 + growth_rate / 100.0) ** i for i in years_range]
fcf_df = pd.DataFrame({'Year': years_range, 'Future FCFE': future_fcfe_list})
st.line_chart(fcf_df.set_index("Year"))

st.subheader("💰 Intrinsic Value Breakdown")
labels = ['Sum of PV(FCFE)', 'PV(Terminal Equity)']
values = [sum(fcfe_pvs), terminal_equity_pv]
if all(v > 0 for v in values):
    fig, ax = plt.subplots()
    ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=90)
    ax.axis('equal')
    st.pyplot(fig)
else:
    st.warning("⚠️ Unable to display pie chart: values must be positive.")

# ----------------------------
# Step 6: Sensitivity Table (FCFE-based)
# ----------------------------
st.markdown("---")
st.subheader("📊 Sensitivity Analysis (constant FCFE toy model)")

discount_rates = [0.07, 0.08, 0.09, 0.10, 0.11]  # as decimals (Cost of Equity scenarios)
growth_rates = [0.02, 0.04, 0.06, 0.08]          # growth scenarios

table = []
for g in growth_rates:
    row = []
    for r in discount_rates:
        intrinsic = 0.0
        for i in range(years):
            intrinsic += base_fcfe * (1 + g) ** (i + 1) / ((1 + r) ** (i + 1))
        try:
            last = base_fcfe * (1 + g) ** years
            terminal = (last * (1 + g)) / (r - g)
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

# Disclaimer
st.markdown("---")
st.caption("This tool is for educational purposes and does not constitute investment advice.")
