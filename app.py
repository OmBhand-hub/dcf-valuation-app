# DCF Valuation App

# Step 1: Get user inputs
print("Welcome to the DCF Valuation App")

fcf = float(input("Enter current Free Cash Flow (in millions): "))
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

