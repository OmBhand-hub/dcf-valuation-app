import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import yfinance as yf
import html  # for safe escaping in the custom panel

# ======================
# Formatting helpers
# ======================
def short_number(n: float) -> str:
    """Return n with M/B/T suffix and commas (no currency symbol)."""
    try:
        n = float(n)
    except Exception:
        return "N/A"
    a = abs(n)
    if a >= 1e12:
        return f"{n/1e12:,.2f}T"
    if a >= 1e9:
        return f"{n/1e9:,.2f}B"
    if a >= 1e6:
        return f"{n/1e6:,.2f}M"
    return f"{n:,.2f}"

def money(n: float, sym: str) -> str:
    """Currency with commas and 2dp (no suffix)."""
    try:
        return f"{sym}{float(n):,.2f}"
    except Exception:
        return f"{sym}0.00"

def money_short(n: float, sym: str) -> str:
    """Currency + short_number."""
    return f"{sym}{short_number(n)}"

def currency_symbol(code: str) -> str:
    return {
        "USD": "$", "INR": "₹", "GBP": "£", "EUR": "€", "JPY": "¥",
        "CNY": "¥", "CAD": "C$", "AUD": "A$", "CHF": "CHF "
    }.get((code or "USD").upper(), f"{code} ")

def green_panel(title: str, lines: list[str]):
    """Stable, uniform green box (no markdown parsing)."""
    safe_title = html.escape(title)
    safe_lines = [html.escape(x) for x in lines]
    st.markdown(
        f"""
        <div style="background:#143D2A;border:1px solid #14532d;border-radius:12px;padding:16px;">
          <div style="font-weight:600;margin-bottom:6px;">{safe_title}</div>
          <div style="line-height:1.6;">{"<br>".join(safe_lines)}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

# ======================
# Data helpers (robust)
# ======================
def resolve_symbol(raw: str) -> str:
    """If user omits Indian suffix, try .NS then .BO; otherwise keep as-is."""
    s = (raw or "").strip().upper()
    if s.endswith((".NS", ".BO")):
        return s
    candidates = [f"{s}.NS", f"{s}.BO"]
    for c in candidates:
        try:
            t = yf.Ticker(c)
            fi = getattr(t, "fast_info", None)
            if fi and (fi.get("last_price") or fi.get("market_cap")):
                return c
        except Exception:
            pass
    return s

def get_current_price(t: yf.Ticker):
    try:
        fi = getattr(t, "fast_info", None)
        if fi and fi.get("last_price"):
            return float(fi["last_price"])
    except Exception:
        pass
    try:
        info = t.info
        if info and info.get("currentPrice"):
            return float(info["currentPrice"])
    except Exception:
        pass
    try:
        h = t.history(period="1d")
        if not h.empty:
            return float(h["Close"].iloc[-1])
    except Exception:
        pass
    return None

def get_debt_value(t: yf.Ticker) -> float:
    """Try Total Debt; else sum common components; else last-resort liabilities."""
    try:
        for bs in (t.balance_sheet, t.quarterly_balance_sheet):
            if bs is None or bs.empty:
                continue
            idx_lower = {str(i).strip().lower(): i for i in bs.index}
            def row(name_variants):
                for nm in name_variants:
                    key = nm.lower()
                    if key in idx_lower:
                        return bs.loc[idx_lower[key]]
                return None

            # 1) Direct total debt if available
            r_total_debt = row(["Total Debt"])
            if r_total_debt is not None:
                return float(pd.Series(r_total_debt).dropna().iloc[0])

            # 2) Build from parts
            parts = []
            for nm in ["Long Term Debt", "Long-Term Debt", "Short Long Term Debt",
                       "Current Portion Of Long Term Debt", "Short Term Debt", "Short-Term Debt"]:
                r = row([nm])
                if r is not None:
                    parts.append(pd.Series(r))
            if parts:
                return float(pd.concat(parts, axis=1).fillna(0.0).sum(axis=1).dropna().iloc[0])

            # 3) Fall back to total liabilities (proxy) if absolutely nothing else
            r_liab = row(["Total Liab", "Total Liabilities", "Total Liabilities Net Minority Interest"])
            if r_liab is not None:
                return float(pd.Series(r_liab).dropna().iloc[0])
    except Exception:
        pass
    return 0.0

def get_fcfe_series(t: yf.Ticker) -> pd.Series | None:
    """FCFE ≈ Free Cash Flow = CFO - CapEx (Yahoo 'Free Cash Flow'). Return newest->oldest."""
    try:
        cf = t.cashflow
        if cf is None or cf.empty:
            return None
        if "Free Cash Flow" in cf.index:
            return pd.Series(cf.loc["Free Cash Flow"]).dropna()
        if ("Total Cash From Operating Activities" in cf.index) and ("Capital Expenditures" in cf.index):
            op = pd.Series(cf.loc["Total Cash From Operating Activities"]).fillna(0)
            capex = pd.Series(cf.loc["Capital Expenditures"]).fillna(0)
            return (op - capex).dropna()
    except Exception:
        pass
    return None

# ======================
# App
# ======================
st.set_page_config(page_title="DCF Valuation App", layout="centered")
st.title("📊 DCF Valuation App")

st.markdown("""
### How it works
This app values equity using a **FCFE DCF**: we take **Free Cash Flow to Equity** (3-year average),
discount it at the **Cost of Equity**, add a terminal equity value, and divide by shares to get an implied price.
""")

# ---- Step 1: Fetch ----
st.markdown("---")
st.subheader("Step 1: Fetch the company's financials")

raw = st.text_input("Enter stock ticker (e.g., AAPL, MSFT, TATAMOTORS)", value="AAPL")
symbol = resolve_symbol(raw)
fcfe_latest = 0.0
fcfe_avg3 = 0.0
equity_value = 0.0
debt_value = 0.0
sym = "$"
stock = None

if symbol:
    try:
        stock = yf.Ticker(symbol)

        # currency symbol
        code = (stock.info or {}).get("currency", "USD")
        sym = currency_symbol(code)

        # market cap
        fi = getattr(stock, "fast_info", None)
        equity_value = float(
            (fi.get("market_cap") if fi else 0)
            or (stock.info.get("marketCap", 0) if stock.info else 0)
            or 0
        )

        # debt (robust)
        debt_value = float(get_debt_value(stock))

        # FCFE series and averages
        s = get_fcfe_series(stock)
        if s is not None and not s.empty:
            fcfe_latest = float(s.iloc[0])
            fcfe_avg3 = float(s.iloc[:3].mean())
        else:
            fcfe_latest = 0.0
            fcfe_avg3 = 0.0

        # fetched panel
        green_panel(
            f"Fetched values for {symbol}:",
            [
                f"Free Cash Flow to Equity (latest): {money_short(fcfe_latest, sym)}",
                f"Free Cash Flow to Equity (3-yr avg): {money_short(fcfe_avg3, sym)}",
                f"Equity Value (Market Cap): {money_short(equity_value, sym)}",
                f"Debt: {money_short(debt_value, sym)}",
            ],
        )

    except Exception as e:
        st.error(f"❌ Failed to fetch data for {symbol}. Reason: {e}")
        fcfe_latest = fcfe_avg3 = equity_value = debt_value = 0.0

# ---- Step 2: Discount rate (Cost of Equity) ----
st.markdown("---")
st.subheader("Step 2: Set the discount rate (Cost of Equity)")

cost_of_equity_pct = st.number_input("Cost of Equity (%)", min_value=0.0, max_value=30.0, value=10.0, step=0.5)
ke = cost_of_equity_pct / 100.0
st.info(f"Using Cost of Equity: **{cost_of_equity_pct:.2f}%**")

# ---- Step 3: Projection (FCFE) ----
st.markdown("---")
st.subheader("Step 3: Project the company’s future cash flows (FCFE)")

growth_pct = st.number_input("Expected annual growth rate (%)", min_value=0.0, value=6.0, step=0.5)
years = st.slider("Number of years to project", min_value=1, max_value=10, value=5)
terminal_growth_pct = st.number_input("Terminal growth rate (%)", min_value=0.0, value=2.0, step=0.5)

g = growth_pct / 100.0
tg = terminal_growth_pct / 100.0
base_fcfe = fcfe_avg3

# Guardrail: terminal growth must be < discount rate
if ke <= tg and (ke > 0):
    st.warning("Terminal growth is ≥ discount rate; capping terminal growth to (discount - 0.5%).")
    tg = max(0.0, ke - 0.005)

# PV of projected FCFE
pv_fcfe = []
for i in range(1, years + 1):
    future = base_fcfe * ((1 + g) ** i)
    pv = future / ((1 + ke) ** i)
    pv_fcfe.append(pv)

# Terminal equity value (Gordon)
terminal_equity = 0.0
if ke > tg:
    last = base_fcfe * ((1 + g) ** years)
    terminal_equity = (last * (1 + tg)) / (ke - tg)
terminal_equity_pv = terminal_equity / ((1 + ke) ** years) if terminal_equity > 0 else 0.0

intrinsic_equity_value = sum(pv_fcfe) + terminal_equity_pv

st.subheader("Estimated Intrinsic Value (DCF)")
st.metric("Intrinsic Equity Value", money_short(intrinsic_equity_value, sym))

# ---- Step 4: Compare to market price ----
st.markdown("---")
st.subheader("Step 4: Compare to market price")

# shares & current price
shares_outstanding = 0
current_price = None
try:
    shares_outstanding = int(
        (getattr(stock, "fast_info", {}) or {}).get("shares_outstanding")
        or (stock.info.get("sharesOutstanding", 0) if stock and stock.info else 0)
        or 0
    )
except Exception:
    shares_outstanding = 0
current_price = get_current_price(stock) if stock else None

if shares_outstanding > 0:
    implied_price = intrinsic_equity_value / shares_outstanding
    mos = st.slider("Margin of Safety (%)", min_value=0, max_value=50, value=20, step=5)
    target_price = implied_price * (1 - mos / 100.0)

    # badge
    if current_price is not None:
        if current_price < target_price:
            st.markdown("<span style='color:green;font-weight:bold;font-size:18px;'>✅ Undervalued</span>", unsafe_allow_html=True)
        elif current_price > implied_price:
            st.markdown("<span style='color:red;font-weight:bold;font-size:18px;'>❌ Overvalued</span>", unsafe_allow_html=True)
        else:
            st.markdown("<span style='color:orange;font-weight:bold;font-size:18px;'>⚖️ Fairly Valued</span>", unsafe_allow_html=True)

    cols = st.columns(3)
    with cols[0]:
        st.metric("Implied Price (DCF)", money(implied_price, sym))
    with cols[1]:
        st.metric("Current Price", money(current_price if current_price is not None else 0.0, sym))
    with cols[2]:
        st.metric(f"Target Buy (MOS {mos}%)", money(target_price, sym))
else:
    st.warning("⚠️ Could not fetch shares outstanding to calculate implied share price.")

# ---- Visuals ----
st.markdown("---")
st.subheader("📈 Projected Free Cash Flows (FCFE)")

years_range = list(range(1, years + 1))
future_fcfe_list = [base_fcfe * ((1 + g) ** i) for i in years_range]
fcf_df = pd.DataFrame({"Year": years_range, "Future FCFE": future_fcfe_list})
st.line_chart(fcf_df.set_index("Year"))

st.subheader("💰 Intrinsic Value Breakdown")
labels = ["Sum of PV(FCFE)", "PV(Terminal Equity)"]
values = [sum(pv_fcfe), terminal_equity_pv]
if all(v > 0 for v in values):
    fig, ax = plt.subplots()
    ax.pie(values, labels=labels, autopct="%1.1f%%", startangle=90)
    ax.axis("equal")
    st.pyplot(fig)
else:
    st.warning("⚠️ Unable to display pie chart: values must be positive.")

# ---- Sensitivity (nicely formatted with commas) ----
st.markdown("---")
st.subheader("📊 Sensitivity Analysis (millions, formatted)")

disc_rates = [0.07, 0.08, 0.09, 0.10, 0.11]
growth_opts = [0.02, 0.04, 0.06, 0.08]

table = []
for g2 in growth_opts:
    row = []
    for r in disc_rates:
        total = 0.0
        for i in range(1, years + 1):
            total += base_fcfe * ((1 + g2) ** i) / ((1 + r) ** i)
        if r > g2:
            last = base_fcfe * ((1 + g2) ** years)
            term = (last * (1 + g2)) / (r - g2)
            total += term / ((1 + r) ** years)
        row.append(total / 1e6)  # show in millions
    table.append(row)

df_sens = pd.DataFrame(
    table,
    index=[f"{int(g*100)}%" for g in growth_opts],
    columns=[f"{int(r*100)}%" for r in disc_rates],
)
st.dataframe(df_sens.style.format("{:,.2f}"), height=260)

# ---- Footer ----
st.markdown("---")
st.caption("This tool is for educational purposes and does not constitute investment advice.")
st.markdown("© 2025 Om Bhand. All rights reserved.", unsafe_allow_html=True)
