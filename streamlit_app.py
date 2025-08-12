import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import yfinance as yf

# --- Helper function for number formatting ---
def money_short(x):
    """$ with M/B/T suffix and 2 dp."""
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

# --- Streamlit setup ---
st.set_page_config(page_title="DCF Valuation App", layout="centered")
st.title("📊 DCF Valuation App")

# --- Intro / How it works ---
st.markdown("""
### How it works
This app estimates a company's intrinsic value using a **Discounted Cash Flow (DCF)** model.
You enter a stock ticker, we auto-fetch key financials (Market Cap, Debt, Free Cash Flow), 
project future cash flows, discount them using WACC, and compare the result to the current market price.

**Main steps:**
1. Fetch financial data for the ticker.
2. Project future free cash flows.
3. Discount them back to today using WACC.
4. Add a terminal value for beyond the forecast period.
5. Compare the implied share price to the current market price, factoring in your Margin of Safety.
""")

# --- Step 1: Fetch financials ---
st.markdown("---")
st.subheader("Step 1: Fetch the company's financials")

ticker = st.text_input("Enter stock ticker (e.g., AAPL, MSFT, TSLA)", value="AAPL")

fcf = 0
equity_value = 0
debt_value = 0

if ticker:
    try:
        stock = yf.Ticker(ticker)

        # --- EQUITY VALUE ---
        equity_value = stock.info.get("marketCap", 0)

        # --- DEBT VALUE (robust search) ---
        try:
            debt_value = 0
            bs_sources = [stock.balance_sheet, stock.quarterly_balance_sheet]
            for bs in bs_sources:
                if bs is not None and not bs.empty:
                    matches = [idx for idx in bs.index if "total liab" in idx.lower() or "total liabilities" in idx.lower()]
                    if matches:
                        debt_value = bs.loc[matches[0]].dropna().values[0]
                        break
            debt_value = float(debt_value or 0)
        except Exception as e:
            st.warning(f"⚠️ Couldn't extract debt: {e}")
            debt_value = 0

        # --- FREE CASH FLOW ---
        cashflow = stock.cashflow
        try:
            if "Free Cash Flow" in cashflow.index:
                fcf = float(cashflow.loc["Free Cash Flow"][0])
            elif (
                "Total Cash From Operating Activities" in cashflow.index
                and "Capital Expenditures" in cashflow.index
            ):
                op_cf = float(cashflow.loc["Total Cash From Operating Activities"][0])
                capex = float(cashflow.loc["Capital Expenditures"][0])
                fcf = op_cf - capex
        except Exception as e:
            st.warning(f"⚠️ Couldn't extract FCF: {e}")

        # Ensure defaults if missing
        fcf = fcf or 0
        equity_value = equity_value or 0
        debt_value = debt_value or 0

        # --- Display fetched values ---
        st.success(
            f"Fetched values for {ticker.upper()}:\n\n"
            f"• Free Cash Flow: **{money_short(fcf)}**\n"
            f"• Equity Value (Market Cap): **{money_short(equity_value)}**\n"
            f"• Debt: **{money_short(debt_value)}**"
        )

    except Exception as e:
        st.error(f"❌ Failed to fetch data for {ticker.upper()}. Reason: {e}")
        fcf = 0
        equity_value = 0
        debt_value = 0

# --- Step 2: Project cash flows ---
st.markdown("---")
st.subheader("Step 2: Project the company's future cash flows")

tax_rate = st.number_input("Corporate Tax Rate (%)", min_value=0.0, max_value=100.0, value=21.0, step=0.1)
total_value = equity_value + debt_value

if total_value > 0:
    cost_of_equity = 10
    cost_of_debt = 5
    wacc = ((equity_value / total_value) * (cost_of_equity / 100)) + \
           ((debt_value / total_value) * (cost_of_debt / 100) * (1 - tax_rate / 100))
    st.info(f"Calculated WACC: **{wacc:.2%}**")
else:
    wacc = 0
    st.warning("⚠️ Enter valid equity and debt values to calculate WACC.")

growth_rate = st.number_input("Expected annual growth rate (%)", min_value=0.0, value=5.0, step=0.5)
years = st.slider("Number of years to project", min_value=1, max_value=10, value=5)
terminal_growth = st.number_input("Terminal growth rate (%)", min_value=0.0, value=2.0, step=0.5)

# --- Step 3: DCF Calculation ---
st.markdown("---")
st.subheader("Step 3: Calculate intrinsic value")

fcf_list = []
for i in range(1, years + 1):
    future_fcf = fcf * (1 + growth_rate / 100) ** i
    discounted_fcf = future_fcf / ((1 + wacc) ** i)
    fcf_list.append(discounted_fcf)

last_fcf = fcf * (1 + growth_rate / 100) ** years
try:
    terminal_value = (last_fcf * (1 + terminal_growth / 100)) / (wacc - terminal_growth / 100)
except ZeroDivisionError:
    terminal_value = 0
discounted_terminal = terminal_value / ((1 + wacc) ** years)

dcf_value = sum(fcf_list) + discounted_terminal
st.success(f"💰 Estimated Intrinsic Value: **{money_short(dcf_value*1e6)}**")

# --- Step 4: Implied price & valuation ---
st.markdown("---")
st.subheader("Step 4: Compare to market price")

shares_outstanding = stock.info.get("sharesOutstanding", 0)
if shares_outstanding and shares_outstanding > 0:
    implied_price = (dcf_value * 1e6) / shares_outstanding
    current_price = stock.history(period="1d")["Close"].iloc[-1]
    margin_safety = st.slider("Margin of Safety (%)", min_value=0, max_value=50, value=20)
    target_price = implied_price * (1 - margin_safety / 100)

    if current_price < target_price:
        st.markdown(f"<span style='color:green;font-weight:bold'>✅ Undervalued</span>", unsafe_allow_html=True)
    elif current_price > implied_price:
        st.markdown(f"<span style='color:red;font-weight:bold'>❌ Overvalued</span>", unsafe_allow_html=True)
    else:
        st.markdown(f"<span style='color:orange;font-weight:bold'>⚠️ Fairly Valued</span>", unsafe_allow_html=True)

    st.write(f"**Implied Price:** ${implied_price:.2f}")
    st.write(f"**Current Price:** ${current_price:.2f}")
    st.write(f"**Target Price (with MOS):** ${target_price:.2f}")
else:
    st.warning("⚠️ Could not fetch shares outstanding to calculate implied share price.")

# --- Step 5: Charts ---
st.markdown("---")
st.subheader("📈 Projected Free Cash Flows")
years_range = list(range(1, years + 1))
future_fcf_list = [fcf * (1 + growth_rate / 100) ** i for i in years_range]
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

# --- Step 6: Sensitivity Analysis ---
st.markdown("---")
st.subheader("📊 Sensitivity Analysis")
discount_rates = [0.08, 0.09, 0.10, 0.11, 0.12]
growth_rates = [0.01, 0.02, 0.03, 0.04, 0.05]
table = []
for g in growth_rates:
    row = []
    for r in discount_rates:
        intrinsic = sum(fcf / ((1 + r) ** (i + 1)) for i in range(years))
        try:
            terminal = (fcf * (1 + g)) / (r - g)
        except ZeroDivisionError:
            terminal = 0
        terminal /= (1 + r) ** years
        total_val = intrinsic + terminal
        row.append(round(total_val, 2))
    table.append(row)
df_table = pd.DataFrame(
    table,
    index=[f"{int(g*100)}%" for g in growth_rates],
    columns=[f"{int(r*100)}%" for r in discount_rates]
)
st.dataframe(df_table.style.format("{:.2f}"), height=250)

# --- Disclaimer ---
st.markdown("---")
st.caption("This tool is for educational purposes and does not constitute investment advice.")
