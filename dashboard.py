# pro_dashboard.py
# Full dashboard: price, positions, EUR%, PnL, normalized capital, leaderboard, recent trades
# pip install requests

import os
import time
import requests
from datetime import datetime

URL = "http://fx-trading-game-ensimag-challenge.westeurope.azurecontainer.io:443"
PRODUCT = "EURGBP"
TRADER_ID = "yhhwsgzliKCtrelXLf48EoRuYeb9lPo8"
REFRESH_SECONDS = 1

# PnL baseline mode:
USE_FIXED_BASELINE = False           # True -> use FIXED_BASELINE_EUR_EQUIV; False -> first read from server
FIXED_BASELINE_EUR_EQUIV = 1_000_000

# =============== API ===============
def get_price():
    try:
        r = requests.get(f"{URL}/price/{PRODUCT}", timeout=3)
        if r.status_code == 200:
            j = r.json()
            return j.get("price"), j.get("time")
    except Exception:
        pass
    return None, None

def get_positions():
    try:
        r = requests.get(f"{URL}/positions/{TRADER_ID}", timeout=3)
        if r.status_code == 200:
            return r.json()  # {"EUR": ..., "GBP": ...}
    except Exception:
        pass
    return {}

def get_normalized_capitals():
    try:
        r = requests.get(f"{URL}/normalizedCapitals", timeout=3)
        if r.status_code == 200:
            return r.json()  # { "Trader1": 1000000.12, ... } in GBP
    except Exception:
        pass
    return {}

def get_trade_history():
    try:
        r = requests.get(f"{URL}/tradeHistory", timeout=3)
        if r.status_code == 200:
            return r.json()  # list of trades
    except Exception:
        pass
    return []

# =============== Helpers ===============
def clear():
    os.system("cls" if os.name == "nt" else "clear")

def eur_equiv(eur_units, gbp_units, price):
    if not price or price <= 0:
        return None
    return eur_units + (gbp_units / price)

def gbp_equiv(eur_units, gbp_units, price):
    if not price or price <= 0:
        return None
    return gbp_units + (eur_units * price)

def eur_share(eur_units, gbp_units, price):
    te = eur_equiv(eur_units, gbp_units, price)
    if te is None or te <= 0:
        return None
    return eur_units / te

def fmt(x, digits=2):
    if x is None:
        return "-"
    try:
        return f"{x:,.{digits}f}"
    except Exception:
        return str(x)

def now_str():
    return datetime.now().strftime("%H:%M:%S")

def last_trade_snapshot(trades):
    if not trades or not isinstance(trades, list):
        return None
    t = trades[-1]
    try:
        return {
            "time": t.get("time"),
            "user": t.get("User_name"),
            "side": t.get("side"),
            "qty": t.get("quantity"),
            "pair": t.get("pair"),
            "rate": t.get("rate"),
        }
    except Exception:
        return None

# =============== Main loop ===============
def main():
    baseline_eur_equiv = None
    if USE_FIXED_BASELINE:
        baseline_eur_equiv = FIXED_BASELINE_EUR_EQUIV

    while True:
        price, ts = get_price()
        pos = get_positions()
        eur_units = float(pos.get("EUR", 0.0))
        gbp_units = float(pos.get("GBP", 0.0))

        te = eur_equiv(eur_units, gbp_units, price)  # total in EUR
        tg = gbp_equiv(eur_units, gbp_units, price)  # total in GBP
        share = eur_share(eur_units, gbp_units, price)

        # Initialize baseline from first valid total if using auto-baseline
        if not USE_FIXED_BASELINE and baseline_eur_equiv is None and te is not None and te > 0:
            baseline_eur_equiv = te

        pnl_abs = pnl_pct = None
        if baseline_eur_equiv and te is not None:
            pnl_abs = te - baseline_eur_equiv
            pnl_pct = 100.0 * pnl_abs / baseline_eur_equiv

        capitals = get_normalized_capitals()
        my_norm_gbp = None
        if isinstance(capitals, dict) and TRADER_ID in capitals:
            try:
                my_norm_gbp = float(capitals[TRADER_ID])
            except Exception:
                my_norm_gbp = None

        # Leaderboard top 5
        leaderboard = []
        if isinstance(capitals, dict) and capitals:
            try:
                leaderboard = sorted(
                    [(k, float(v)) for k, v in capitals.items()],
                    key=lambda x: x[1],
                    reverse=True
                )[:5]
            except Exception:
                leaderboard = []

        trades = get_trade_history()
        recent_count = len(trades) if isinstance(trades, list) else 0
        last_t = last_trade_snapshot(trades)

        # Render
        clear()
        print("=== Morgan Stanley Trading Game — Pro Dashboard ===")
        print(f"Trader ID: {TRADER_ID}     Time: {now_str()}")
        print("---------------------------------------------------")
        print(f" Live Price (EURGBP):   {price if price is not None else '-'}   (ts: {ts})")
        print("---------------------------------------------------")
        print(f" EUR:                   {fmt(eur_units, 2)}")
        print(f" GBP:                   {fmt(gbp_units, 2)}")
        if share is not None:
            status = "OK" if share >= 0.30 else "WARNING < 30%"
            print(f" EUR Share:             {share*100:5.2f}%   [{status}]")
        else:
            print(" EUR Share:             -")
        print(f" Total (EUR equiv):     {fmt(te, 2)}")
        print(f" Total (GBP equiv):     {fmt(tg, 2)}")
        print("---------------------------------------------------")
        if baseline_eur_equiv is not None:
            print(f" Baseline (EUR equiv):  {fmt(baseline_eur_equiv, 2)}")
        else:
            print(" Baseline (EUR equiv):  waiting for first valid read...")
        if pnl_abs is not None:
            sign = "+" if pnl_abs >= 0 else ""
            print(f" PnL:                   {sign}{fmt(pnl_abs, 2)} EUR  ({sign}{fmt(pnl_pct, 2)}%)")
        else:
            print(" PnL:                   -")
        print("---------------------------------------------------")
        print(f" Normalized Capital (GBP): {fmt(my_norm_gbp, 2)}")
        if leaderboard:
            print(" Leaderboard (Top 5 by normalized GBP):")
            for rank, (name, val) in enumerate(leaderboard, start=1):
                mark = "← you" if name == TRADER_ID else ""
                print(f"   {rank}. {name[:24]:24}  {fmt(val, 2)} {mark}")
        else:
            print(" Leaderboard:           -")
        print("---------------------------------------------------")
        if last_t:
            print(f" Recent trades:         {recent_count}")
            print(f" Last trade:            {last_t.get('pair')} {last_t.get('side')} "
                  f"{last_t.get('qty')} @ {last_t.get('rate')}  by {last_t.get('user')}  (t={last_t.get('time')})")
        else:
            print(f" Recent trades:         {recent_count}")
            print(" Last trade:            -")
        print("===================================================")

        time.sleep(REFRESH_SECONDS)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
