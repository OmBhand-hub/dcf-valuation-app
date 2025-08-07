import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import yfinance as yf

st.set_page_config(page_title="DCF Valuation App", layout="centered")
st.title("📊 DCF Valuation App")

st.subheader("Enter Stock Ticker to Auto-Fill Financials")
ticker = st.text_input("Enter stock ticker (e.g., AAPL, MSFT, TSLA)", value="AAPL")

fcf = 0
equity_value = 0
debt_value = 0

if ticker:
    try:
        stock = yf.Ticker(ticker)

        # Fetch Market Cap (Equity Value)
        equity_value = stock.info.get("marketCap", 0)

        # Fetch Total Liabilities (as proxy for debt)
        balance_sheet = stock.balance_sheet
        st.write("📄 Raw Balance Sheet:")
        st.dataframe(balance_sheet)

        try:
            debt_value = float(balance_sheet.loc["Total Liab"][0])
        except:
            debt_value = 0


        # Fetch Free Cash Flow
        cashflow = stock.cashflow
        st.write("📄 Raw Cash Flow Statement:")
        st.dataframe(cashflow)

        try:
            operating_cf = float(cashflow.loc["Total Cash From Operating Activities"][0])
            capex = float(cashflow.loc["Capital Expenditures"][0])
            fcf = operating_cf - capex
        except:
            fcf = 0


        fcf = fcf or 0
        equity_value = equity_value or 0
        debt_value = debt_value or 0

        st.success(f"Fetched values for {ticker.upper()}: FCF = {fcf/1e6:.1f}M, Equity = ${equity_value:,}, Debt = ${debt_value:,}")

    except Exception as e:
        st.warning("Could not fetch data. Please check the ticker or try again later.")

st.markdown("Estimate the intrinsic value of a company using a Discounted Cash Flow (DCF) model.")

# WACC Calculation
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
st.subheader("Step 2: DCF Inputs")

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
st.subheader(f"💰 Estimated Intrinsic Value: **${round(dcf_value, 2)} million**")

# Implied Share Price
shares_outstanding = 0
try:
    shares_outstanding = stock.info.get("sharesOutstanding", 0)
except:
    pass

if shares_outstanding and shares_outstanding > 0:
    implied_price = (dcf_value * 1e6) / shares_outstanding
    st.write(f"📊 **Implied Share Price:** ${implied_price:.2f}")
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

st.markdown("© 2025 Om Bhand. All rights reserved.", unsafe_allow_html=True)
