import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import yfinance as yf

st.set_page_config(page_title="DCF Valuation App", layout="centered")
st.title("📊 DCF Valuation App")

st.markdown("""
Estimate the intrinsic value of a company using a Discounted Cash Flow (DCF) model.
""")

# Company Ticker Input
ticker = st.text_input("Enter Ticker Symbol (e.g., AAPL, MSFT, TSLA)").upper()

if ticker:
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        st.subheader(f"📄 Company Overview: {info.get('shortName', 'N/A')}")
        st.write(f"**Sector:** {info.get('sector', 'N/A')}")
        st.write(f"**Industry:** {info.get('industry', 'N/A')}")
        st.write(f"**Market Cap:** ${round(info.get('marketCap', 0)/1e9,2)} Billion")
        st.write(f"**Trailing P/E:** {info.get('trailingPE', 'N/A')}")
        st.write(f"**Beta:** {info.get('beta', 'N/A')}")

    except:
        st.error("Could not fetch data. Please check the ticker.")

st.markdown("---")
st.subheader("Step 1: Calculate WACC (Weighted Average Cost of Capital)")

equity_value = st.number_input("Equity Value (£)", min_value=0.0, step=100000.0)
debt_value = st.number_input("Debt Value (£)", min_value=0.0, step=100000.0)
cost_of_equity = st.number_input("Cost of Equity (%)", min_value=0.0, max_value=100.0, step=0.1)
cost_of_debt = st.number_input("Cost of Debt (%)", min_value=0.0, max_value=100.0, step=0.1)
tax_rate = st.number_input("Corporate Tax Rate (%)", min_value=0.0, max_value=100.0, step=0.1)

total_value = equity_value + debt_value

if total_value > 0:
    wacc = ((equity_value / total_value) * (cost_of_equity / 100)) + ((debt_value / total_value) * (cost_of_debt / 100) * (1 - tax_rate / 100))
    st.success(f"Calculated WACC: {wacc:.2%}")
else:
    wacc = 0
    st.warning("Enter equity and debt values to calculate WACC.")

st.markdown("---")
st.subheader("Step 2: DCF Inputs")

fcf = st.number_input("Enter current Free Cash Flow (in millions)", min_value=0.0, value=100.0, step=10.0)
growth_rate = st.number_input("Expected annual growth rate (%)", min_value=0.0, value=5.0, step=0.5)
discount_rate = wacc
st.markdown(f"**Calculated WACC as Discount Rate:** {wacc*100:.2f}%")
years = st.slider("Number of years to project", min_value=1, max_value=10, value=5)
terminal_growth = st.number_input("Terminal growth rate (%)", min_value=0.0, value=2.0, step=0.5)

# DCF calculation
fcf_list = []
for i in range(1, years + 1):
    future_fcf = fcf * (1 + growth_rate / 100) ** i
    discounted_fcf = future_fcf / ((1 + discount_rate / 100) ** i)
    fcf_list.append(discounted_fcf)

# Terminal value
last_fcf = fcf * (1 + growth_rate / 100) ** years
terminal_value = (last_fcf * (1 + terminal_growth / 100)) / (discount_rate / 100 - terminal_growth / 100)
discounted_terminal = terminal_value / ((1 + discount_rate / 100) ** years)

dcf_value = sum(fcf_list) + discounted_terminal
st.subheader(f"💰 Estimated Intrinsic Value: **${round(dcf_value, 2)} million**")

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


st.subheader("📊 Sensitivity Analysis")

# Ranges
discount_rates = [0.08, 0.09, 0.10, 0.11, 0.12]
growth_rates = [0.01, 0.02, 0.03, 0.04, 0.05]

table = []
for g in growth_rates:
    row = []
    for r in discount_rates:
        intrinsic = 0
        for i in range(years):
            intrinsic += fcf / ((1 + r) ** (i + 1))
        terminal = (fcf * (1 + g)) / (r - g)
        terminal /= (1 + r) ** years
        total_value = intrinsic + terminal
        row.append(round(total_value, 2))
    table.append(row)

df_table = pd.DataFrame(
    table,
    index=[f"{int(g*100)}%" for g in growth_rates],
    columns=[f"{int(r*100)}%" for r in discount_rates]
)
st.dataframe(df_table.style.format("{:.2f}"), height=250)

st.markdown("© 2025 Om Bhand. All rights reserved.", unsafe_allow_html=True)
