
import time
import json
import requests
import pandas as pd
import numpy as np

URL = "http://fx-trading-game-ensimag-challenge.westeurope.azurecontainer.io:443/"
TRADER_ID = "5TgmRIPU06CO5cUrHoDAPvwuqJjLONM5"


class Side:
    BUY = "buy"
    SELL = "sell"

class API_MS:
    def __init__(self,show_log=False):
        self.trader_id = TRADER_ID
        self.url = URL
        self.show_log = show_log

    def get_price(self):
        api_url = self.url + "/price/EURGBP"
        try:
            res = requests.get(api_url, timeout=5)
            res.raise_for_status()
            if res.status_code == 200:
                return json.loads(res.content.decode('utf-8'))
        except requests.exceptions.ConnectTimeout:
            if self.show_log:
                print("Connection timed out while fetching price.")
                time.sleep(4)  # wait a bit before retrying
                self.get_price()
        except Exception as e:
            if self.show_log:
                print(f"Error fetching price: {e}")
                time.sleep(4)  # wait a bit before retrying
                self.get_price()
    

    def trade(self, qty, side):
        api_url = self.url + "/trade/EURGBP"
        data = {"trader_id": self.trader_id, "quantity": qty, "side": side}
        if self.show_log:
            print(f"Trading {data}")
        res = requests.post(api_url, json=data)
        if res.status_code == 200:
            resp_json = json.loads(res.content.decode('utf-8'))
            if resp_json["success"]:
                return resp_json
        return None

    def history(self):
        api_url = self.url + "/priceHistory/EURGBP"
        res = requests.get(api_url)
        res.raise_for_status()
        if res.status_code == 200:
            return pd.DataFrame(data=json.loads(res.content.decode('utf-8')).items(),
                                columns=["time", "price"])
        return None

    def get_positions(self):
        api_url = self.url + f"/positions/{self.trader_id}"
        res = requests.get(api_url)
        res.raise_for_status()
        if res.status_code == 200:
            return json.loads(res.content.decode('utf-8'))
        return None

    def create_and_save_history_df(self):
        df = self.history()
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        df.to_csv("EURGBP_price_history.csv")
        return df

    def func_first_strat(self):
        capital_gbp = 1000000  # Capital initial
        eur_position = 0

        # 1. Charger l'historique des prix depuis le lancement
        df_history = pd.read_csv("EURGBP_price_history.csv", parse_dates=['time'], index_col='time')
        prices = df_history['price'].values
        # 2. Calculer la moyenne et la volatilité du marché "normal"
        baseline = np.mean(prices)
        volatility = np.std(prices)
        print(f"Moyenne historique : {baseline:.5f}")
        print(f"Volatilité historique : {volatility:.5f}")

        # 3. Boucle d'attente active jusqu'à l'événement Brexit (boom +10%)
        print("⚡️En attente d'un mouvement majeur (ex : Brexit)...")
        while True:
            current_price = self.get_price()
            if not current_price:
                time.sleep(0.5)
                continue

            # Critère simple : prix bondit de plus de 10% par rapport à la moyenne
            if current_price / baseline > 1.10:
                print(f"🚨 Detected BREXIT EVENT! Prix actuel {current_price:.5f} > +10% de la moyenne.")
                # Achat maxi en EUR tant qu'on a le capital
                while capital_gbp > 100000 * current_price:
                    exec_price = self.trade(100000, Side.BUY)
                    if exec_price:
                        print(f"Acheté 100k EUR à {exec_price}")
                        capital_gbp -= 100000 * float(exec_price)
                        eur_position += 100000
                        time.sleep(0.5)  # petite pause pour ne pas spammer l'API
                    else:
                        print("Erreur lors du trade !")
                        break
                print("Fin de la prise de position sur événement.")
                break  # Fin de la stratégie, passera à la gestion post-événement si tu veux

            time.sleep(1)

if __name__ == '__main__':
    api = API_MS()
    print(f"Expected to trade at: {api.get_price()}")
    print(f"Effectively traded at: {api.trade(100, Side.BUY)}")
    print(f"Price history: {api.create_and_save_history_df()}")