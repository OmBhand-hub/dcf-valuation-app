# DCF Valuation App

# Step 1: Get user inputs
print("Welcome to the DCF Valuation App")

import yfinance as yf

ticker = input("Enter stock ticker (e.g., AAPL, MSFT): ").upper()
print(f"\n--- Valuing: {ticker} ---\n")

stock = yf.Ticker(ticker)
info = stock.info

try:
    revenue = info.get("totalRevenue", None)
    ebit = info.get("ebit", None)
    net_income = info.get("netIncome", None)

    if revenue and ebit and net_income:
        print(f"\nFetched Financials for {ticker}:")
        print(f"Revenue: ${revenue:,}")
        print(f"EBIT: ${ebit:,}")
        print(f"Net Income: ${net_income:,}")
    else:
        print("Some financial data is missing.")
except Exception as e:
    print(f"Error fetching data: {e}")

# Use net income as a proxy for FCF
if net_income:
    fcf = round(net_income / 1_000_000, 2)
    print(f"\nUsing Net Income as proxy for FCF: ${fcf} million")
else:
    fcf = float(input("Net income not available. Please enter FCF manually (in millions): "))

growth_rate = float(input("Enter expected annual growth rate (in %): ")) / 100
discount_rate = float(input("Enter discount rate / WACC (in %): ")) / 100
years = int(input("Enter number of years for projection: "))
terminal_growth = float(input("Enter terminal growth rate (in %): ")) / 100


# Step 2: Project future FCFs
fcf_list = []

for i in range(1, years + 1):
    future_fcf = fcf * ((1 + growth_rate) ** i)
    discounted_fcf = future_fcf / ((1 + discount_rate) ** i)
    fcf_list.append(discounted_fcf)

# Step 3: Calculate Terminal Value
last_fcf = fcf * ((1 + growth_rate) ** years)
terminal_value = (last_fcf * (1 + terminal_growth)) / (discount_rate - terminal_growth)
discounted_terminal = terminal_value / ((1 + discount_rate) ** years)

# Step 4: Calculate Total DCF Value
dcf_value = sum(fcf_list) + discounted_terminal

# Step 5: Display result
print(f"\nEstimated Intrinsic Value (in millions): ${round(dcf_value, 2)}")

