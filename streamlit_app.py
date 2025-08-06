import streamlit as st

st.title("📊 DCF Valuation App")

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

st.markdown("Estimate a company's intrinsic value using Discounted Cash Flow (DCF) model.")

# Input fields
fcf = st.number_input("Enter current Free Cash Flow (in millions)", min_value=0.0, value=100.0, step=10.0)
growth_rate = st.number_input("Expected annual growth rate (%)", min_value=0.0, value=5.0, step=0.5)
discount_rate = wacc
st.markdown(f"**Calculated WACC:** {wacc*100:.2f}%")
years = st.slider("Number of years to project", min_value=1, max_value=10, value=5)
terminal_growth = st.number_input("Terminal growth rate (%)", min_value=0.0, value=2.0, step=0.5)

# DCF logic
fcf_list = []
for i in range(1, years + 1):
    future_fcf = fcf * (1 + growth_rate / 100) ** i
    discounted_fcf = future_fcf / ((1 + discount_rate / 100) ** i)
    fcf_list.append(discounted_fcf)

# Terminal value
last_fcf = fcf * (1 + growth_rate / 100) ** years
terminal_value = (last_fcf * (1 + terminal_growth / 100)) / (discount_rate / 100 - terminal_growth / 100)
discounted_terminal = terminal_value / ((1 + discount_rate / 100) ** years)

# Result
dcf_value = sum(fcf_list) + discounted_terminal
st.subheader(f"💰 Estimated Intrinsic Value: **${round(dcf_value, 2)} million**")
st.subheader("📊 Market Multiples Sanity Check (Optional)")

with st.expander("Enter values to get alternative valuation comparisons"):
    net_income = st.number_input("Net Income (in millions)", min_value=0.0, value=0.0)
    pe_ratio = st.number_input("Industry Average P/E Ratio", min_value=0.0, value=15.0)

    ebitda = st.number_input("EBITDA (in millions)", min_value=0.0, value=0.0)
    ev_ebitda = st.number_input("Industry Average EV/EBITDA", min_value=0.0, value=10.0)

# P/E Valuation
if net_income > 0 and pe_ratio > 0:
    pe_valuation = net_income * pe_ratio
    st.markdown(f"**📌 Valuation based on P/E:** ${round(pe_valuation, 2)} million")

# EV/EBITDA Valuation
if ebitda > 0 and ev_ebitda > 0:
    ev_valuation = ebitda * ev_ebitda
    st.markdown(f"**📌 Valuation based on EV/EBITDA:** ${round(ev_valuation, 2)} million")

import pandas as pd
import matplotlib.pyplot as plt

# Chart 1: Projected Free Cash Flows
years_range = list(range(1, years + 1))
future_fcf_list = [fcf * (1 + growth_rate) ** i for i in years_range]

st.subheader("📈 Projected Free Cash Flows")
fcf_df = pd.DataFrame({'Year': years_range, 'Future FCF': future_fcf_list})
st.line_chart(fcf_df.set_index("Year"))

# Chart 2: Intrinsic Value Breakdown
st.subheader("💰 Intrinsic Value Breakdown")
labels = ['Discounted FCF', 'Discounted Terminal Value']
values = [sum(fcf_list), discounted_terminal]
fig, ax = plt.subplots()
ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=90)
ax.axis('equal')
st.pyplot(fig)
st.subheader("📊 Sensitivity Analysis")

# Define ranges
discount_rates = [0.08, 0.09, 0.10, 0.11, 0.12]
growth_rates = [0.01, 0.02, 0.03, 0.04, 0.05]

# Create table
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

# Display table
df_table = pd.DataFrame(
    table,
    index=[f"{int(g*100)}%" for g in growth_rates],
    columns=[f"{int(r*100)}%" for r in discount_rates]
)
st.dataframe(df_table.style.format("{:.2f}"), height=250)
st.markdown("© 2025 Om Bhand. All rights reserved.", unsafe_allow_html=True)
