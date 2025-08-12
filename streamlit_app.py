import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import yfinance as yf

# ======================
# Helper Functions
# ======================
def money_short(n):
    """Format numbers with M/B/T suffix and commas."""
    abs_n = abs(n)
    if abs_n >= 1_000_000_000_000:
        return f"{n/1_000_000_000_000:,.2f}T"
    elif abs_n >= 1_000_000_000:
        return f"{n/1_000_000_000:,.2f}B"
    elif abs_n >= 1_000_000:
        return f"{n/1_000_000:,.2f}M"
    else:
        return f"{n:,.2f}"

def get_currency_symbol(currency_code):
    """Map currency codes to symbols."""
    mapping = {
        "USD": "$",
        "INR": "₹",
        "GBP": "£",
        "EUR": "€",
        "JPY": "¥",
        "CNY": "¥",
        "CAD": "C$",
        "AUD": "A$"
    }
    return mapping.get(currency_code, currency_code + " ")

def resolve_symbol(raw):
    """Try to auto-resolve ticker for Indian stocks if suffix not provided."""
    s = (raw or "").strip().upper()
    if s.endswith((".NS", ".BO")):
        return s
    # Try NSE, then BSE
    candidates = [f"{s}.NS", f"{s}.BO"]
    for c in candidates:
        try:
            t = yf.Ticker(c)
            fi = getattr(t, "fast_info", {}) or {}
            if fi.get("last_price") or fi.get("market_cap"):
                return c
        except Exception:
            pass
    return s  # fallback

# ======================
# Streamlit App
# ======================
st.set_page_config(page_title="DCF Valuation App", layout="centered")
st.title("📊 DCF Valuation App")

st.markdown("""
## How the app works:
1. Enter a stock ticker — the app fetches market cap, debt, and free cash flow.
2. You provide growth, tax, and other assumptions.
3. The app projects future cash flows, discounts them, and adds a terminal value.
4. It calculates the intrinsic value and compares it to the current market price.
5. You'll see if the stock might be undervalued or overvalued.
""")

# Ticker input
raw_ticker = st.text_input("Enter stock ticker (e.g., AAPL, MSFT, TATAMOTORS)", value="AAPL")
ticker = resolve_symbol(raw_ticker)

fcf = 0
equity_value = 0
debt_value = 0
currency_symbol = "$"
current_price = None

if ticker:
    try:
        stock = yf.Ticker(ticker)

        # Get currency symbol
        currency_code = stock.info.get("currency", "USD")
        currency_symbol = get_currency_symbol(currency_code)

        # Equity (market cap)
        fi = getattr(stock, "fast_info", {}) or {}
        equity_value = fi.get("market_cap") or stock.info.get("marketCap", 0) or 0
        equity_value = float(equity_value)

        # Debt
        try:
            balance_sheet = stock.balance_sheet
            if balance_sheet is not None and not balance_sheet.empty:
                if "Total Liab" in balance_sheet.index:
                    debt_value = balance_sheet.loc["Total Liab"].dropna().values[0]
                elif "Total Liab" in balance_sheet.columns:
                    debt_value = balance_sheet["Total Liab"].dropna().values[0]
            debt_value = float(debt_value)
        except Exception as e:
            st.warning(f"⚠️ Couldn't extract debt: {e}")
            debt_value = 0

        # Free Cash Flow
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

        fcf = fcf or 0
        equity_value = equity_value or 0
        debt_value = debt_value or 0

        # Current price
        current_price = fi.get("last_price")
        if not current_price:
            h = stock.history(period="1d")
            if not h.empty:
                current_price = float(h["Close"].iloc[-1])

        # Display fetched values neatly
        st.success(
            f"**Free Cash Flow:** {currency_symbol}{money_short(fcf)}\n"
            f"**Equity Value:** {currency_symbol}{money_short(equity_value)}\n"
            f"**Debt:** {currency_symbol}{money_short(debt_value)}"
        )

    except Exception as e:
        st.error(f"❌ Failed to fetch data for {ticker.upper()}. Reason: {e}")
        fcf = 0
        equity_value = 0
        debt_value = 0

st.markdown("---")
st.subheader("Step 1: Calculate WACC")

tax_rate = st.number_input("Corporate Tax Rate (%)", min_value=0.0, max_value=100.0, value=21.0, step=0.1)
total_value = equity_value + debt_value

if total_value > 0:
    cost_of_equity = 10
    cost_of_debt = 5
    wacc = ((equity_value / total_value) * (cost_of_equity / 100)) + \
           ((debt_value / total_value) * (cost_of_debt / 100) * (1 - tax_rate / 100))
    st.success(f"✅ Calculated WACC: {wacc:.2%}")
else:
    wacc = 0
    st.warning("⚠️ Enter valid equity and debt values to calculate WACC.")

# Step 2: DCF Inputs
st.markdown("---")
st.subheader("Step 2: Project the company's future cash flows")

growth_rate = st.number_input("Expected annual growth rate (%)", min_value=0.0, value=5.0, step=0.5)
discount_rate = wacc
st.markdown(f"**Calculated WACC as Discount Rate:** {wacc*100:.2f}%")
years = st.slider("Number of years to project", min_value=1, max_value=10, value=5)
terminal_growth = st.number_input("Terminal growth rate (%)", min_value=0.0, value=2.0, step=0.5)

# DCF Calculation
fcf_list = []
for i in range(1, years + 1):
    future_fcf = fcf * (1 + growth_rate / 100) ** i
    discounted_fcf = future_fcf / ((1 + discount_rate / 100) ** i)
    fcf_list.append(discounted_fcf)

# Terminal value
last_fcf = fcf * (1 + growth_rate / 100) ** years
try:
    terminal_value = (last_fcf * (1 + terminal_growth / 100)) / (discount_rate / 100 - terminal_growth / 100)
except ZeroDivisionError:
    terminal_value = 0
discounted_terminal = terminal_value / ((1 + discount_rate / 100) ** years)

dcf_value = sum(fcf_list) + discounted_terminal
st.subheader(f"💰 Estimated Intrinsic Value: **{currency_symbol}{round(dcf_value, 2)} million**")

# Implied Share Price & Valuation Status
shares_outstanding = 0
try:
    shares_outstanding = stock.info.get("sharesOutstanding", 0)
except:
    pass

if shares_outstanding and shares_outstanding > 0:
    implied_price = (dcf_value * 1e6) / shares_outstanding
    st.write(f"📊 **Implied Share Price:** {currency_symbol}{implied_price:.2f}")
    if current_price:
        if implied_price > current_price:
            st.markdown(f"<span style='color:green;font-weight:bold'>✅ Undervalued</span>", unsafe_allow_html=True)
        elif implied_price < current_price:
            st.markdown(f"<span style='color:red;font-weight:bold'>❌ Overvalued</span>", unsafe_allow_html=True)
        else:
            st.markdown(f"<span style='color:orange;font-weight:bold'>⚠️ Fairly valued</span>", unsafe_allow_html=True)
else:
    st.warning("⚠️ Could not fetch shares outstanding to calculate implied share price.")

# Charts
years_range = list(range(1, years + 1))
future_fcf_list = [fcf * (1 + growth_rate / 100) ** i for i in years_range]

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

# Sensitivity Table
st.subheader("📊 Sensitivity Analysis")

discount_rates = [0.08, 0.09, 0.10, 0.11, 0.12]
growth_rates = [0.01, 0.02, 0.03, 0.04, 0.05]

table = []
for g in growth_rates:
    row = []
    for r in discount_rates:
        intrinsic = 0
        for i in range(years):
            intrinsic += fcf / ((1 + r) ** (i + 1))
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

# Disclaimer
st.markdown("---")
st.caption("This tool is for educational purposes and does not constitute investment advice.")

st.markdown("© 2025 Om Bhand. All rights reserved.", unsafe_allow_html=True)
