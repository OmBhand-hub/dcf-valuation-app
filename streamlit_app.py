import streamlit as st

st.title("📊 DCF Valuation App")

st.markdown("Estimate a company's intrinsic value using Discounted Cash Flow (DCF) model.")

# Input fields
fcf = st.number_input("Enter current Free Cash Flow (in millions)", min_value=0.0, value=100.0, step=10.0)
growth_rate = st.number_input("Expected annual growth rate (%)", min_value=0.0, value=5.0, step=0.5)
discount_rate = st.number_input("Discount rate / WACC (%)", min_value=0.0, value=10.0, step=0.5)
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
