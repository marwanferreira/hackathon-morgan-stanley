
from collections import deque
import math
import time
from algo import API_MS
import requests

class Stats:
    def __init__(self, price_len=120, vol_len=40, breakout_len=20):
        self.prices = deque(maxlen=price_len)
        self.returns = deque(maxlen=vol_len)       # log returns for volatility
        self.window_breakout = deque(maxlen=breakout_len)
        self.ema = None

    def update(self, p):
        if self.prices:
            last = self.prices[-1]
            r = math.log(p / last)
            self.returns.append(r)
        self.prices.append(p)
        self.window_breakout.append(p)
        # EMA (30s): alpha = 2/(N+1). N=30
        alpha = 2 / (30 + 1)
        self.ema = p if self.ema is None else (alpha * p + (1 - alpha) * self.ema)

    def vol(self):
        # standard deviation of returns over the last vol_len samples
        n = len(self.returns)
        if n < 2: return 0.0
        mu = sum(self.returns) / n
        var = sum((x - mu) ** 2 for x in self.returns) / (n - 1)
        return math.sqrt(var)

    def high20(self):
        return max(self.window_breakout) if self.window_breakout else None

    def low20(self):
        return min(self.window_breakout) if self.window_breakout else None

class CUSUM:
    # Simple drift detector: accumulates returns until a threshold is exceeded
    def __init__(self, k=0.0, h=0.0):
        self.k = k  # small offset: ignore tiny noise
        self.h = h  # threshold to trigger
        self.pos = 0.0
        self.neg = 0.0

    def set_from_vol(self, sigma_r):
        self.k = 0.2 * sigma_r
        self.h = 3.0 * sigma_r

    def update(self, r):
        self.pos = max(0.0, self.pos + r - self.k)
        self.neg = min(0.0, self.neg + r + self.k)
        up = self.pos > self.h
        down = self.neg < -self.h
        if up: self.pos = 0.0
        if down: self.neg = 0.0
        # return +1 for up-move, -1 for down-move, 0 for nothing
        return (1 if up else (-1 if down else 0))

class Strategy:
    def __init__(self,show_log=False):
        self.show_log = show_log
        self.api = API_MS(self.show_log)
        self.stats = Stats()
        self.cusum = CUSUM()
        self.mode = 'normal'  # or 'event_up', 'event_down'
        self.entry_price = None
        self.peak = None
        self.trough = None
        self.trade_gbp_limit = 100000
        self.max_normal = 300000
        self.max_event = 800000
        self.target_share = 0.40
        self.last_breakout_ts = 0
        self.will_close = False

    def portfolio(self, price):
        inv = self.api.get_positions()  # {'EUR': eur, 'GBP': gbp}
        if self.show_log:
            print(f"Positions: {inv}")
        eur, gbp = inv['EUR'], inv['GBP']
        V = gbp + price * eur
        share = 0.0 if V <= 0 else (price * eur) / V
        return eur, gbp, V, share

    def max_eur_per_trade(self, price):
        return self.trade_gbp_limit / price

    def on_tick(self, price):
        # 1) Update stats
        prev_price = self.stats.prices[-1] if self.stats.prices else None
        self.stats.update(price)
        if len(self.stats.returns) < 30:  # warm-up period
            return

        sigma_r = self.stats.vol()                  # volatility in return units
        sigma_p = price * sigma_r                   # translate to price units
        if self.cusum.h == 0.0:
            self.cusum.set_from_vol(sigma_r)
        r = math.log(price / prev_price) if prev_price else 0.0
        cus = self.cusum.update(r)

        ema = self.stats.ema
        high20 = self.stats.high20()
        low20 = self.stats.low20()
        z = 0.0 if sigma_p == 0 else (price - ema) / sigma_p  # "how far from average"

    
        eur, gbp, V, share = self.portfolio(price)
        notional_eur = price * eur

        # 2) Detect calm vs moving
        z_entry = 2.5  # require a strong move
        breakout_up = ((price > high20) and (z > z_entry)) or (cus == 1)
        breakout_dn = ((price < low20)  and (z < -z_entry)) or (cus == -1)

        # 3) Switch modes if needed
        if self.mode == 'normal':
            if breakout_up:
                self.mode = 'event_up'
                self.entry_price = price
                self.peak = price
            elif breakout_dn:
                self.mode = 'event_down'
                self.entry_price = price
                self.trough = price

        if self.show_log:
            print(f"Price: {price:.5f}, z: {z:.2f}, σ_p: {sigma_p:.5f}, mode: {self.mode}, "
                  f"cus: {cus}, share: {share:.2%}, V: {V:,.0f} GBP")
            print(f'Mode details: entry: {self.entry_price}, peak: {self.peak}, trough: {self.trough}')
        # 4) Act based on mode
        max_per_trade_eur = self.max_eur_per_trade(price)

        if self.mode == 'event_up':
            self.peak = max(self.peak, price)
            trail_price = self.peak * (1 - 0.007)  # 0.7% trailing stop
            # add only if continuing and under cap
            cap = self.max_event
            if price > self.entry_price and price >= high20 and notional_eur < cap:
                size = min(max_per_trade_eur, (cap - notional_eur) / price)
                if size > 0:
                    self.api.trade(size, side='buy')
            # exit on trailing stop
            if price < trail_price:
                self.mode = 'normal'

        elif self.mode == 'event_down':
            self.trough = min(self.trough, price)
            trail_price = self.trough * (1 + 0.007)
            cap = self.max_event
            if price < self.entry_price and price <= low20 and notional_eur > -cap:
                size = min(max_per_trade_eur, (cap + price * (-eur)) / price)
                if size > 0:
                    self.api.trade(size, side='sell')
            if price > trail_price:
                self.mode = 'normal'

        if self.mode == 'normal':
        # Mean reversion with aggressive entries (free fees)
            if sigma_r > 0:
                if z < -0.5 and notional_eur < self.max_normal:
                    # Go long aggressively
                    size = min(max_per_trade_eur, (self.max_normal - notional_eur) / price)
                    if size > 0:
                        self.api.trade(size, side='buy')   # full size, no half
                elif z > 0.5 and notional_eur > -self.max_normal:
                    # Go short aggressively
                    size = min(max_per_trade_eur, (self.max_normal + price * (-eur)) / price)
                    if size > 0:
                        self.api.trade(size, side='sell')
                
                # Exit quickly when z reverts
                if abs(z) < 0.2 and abs(notional_eur) > 0:
                    # flatten position to capture profits
                    if notional_eur > 0:
                        self.api.trade(notional_eur / price, side='sell')
                    else:
                        self.api.trade(-notional_eur / price, side='buy')


        # 5) End-of-exercise rebalance to ~40% EUR
        if self.will_close :
            target_share = self.target_share
            V = gbp + price * eur
            target_eur = (target_share * V) / price
            delta_eur = target_eur - eur
            step = max(-max_per_trade_eur, min(max_per_trade_eur, delta_eur))
            if abs(step) > 1e-6:
                if step > 0 and gbp >= step * price:
                    self.api.trade(step, side='buy')
                elif step < 0 and eur >= -step:
                    self.api.trade(-step, side='sell')

    def run(self):
        print("Starting strategy...")
        while True:
            price_data = self.api.get_price()
            if price_data :
                if price_data.get('price', None):
                    if self.show_log:
                        print(f"Price data: {price_data}")
                    price = float(price_data['price'])
                    self.on_tick(price)
            time.sleep(1)  # wait before next tick
