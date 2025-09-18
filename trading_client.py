# python -m pip install requests

import json
import requests

URL = "http://fx-trading-game-ensimag-challenge.westeurope.azurecontainer.io/:443"
TRADER_ID = "your_trader_id_here"


class Side:
    BUY = "buy"
    SELL = "sell"


def get_price():
    api_url = URL + "/price/EURGBP"
    res = requests.get(api_url)
    if res.status_code == 200:
        return json.loads(res.content.decode('utf-8'))["price"]
    return None


def trade(trader_id, qty, side):
    api_url = URL + "/trade/EURGBP"
    data = {"trader_id": trader_id, "quantity": qty, "side": side}
    res = requests.post(api_url, json=data)
    if res.status_code == 200:
        resp_json = json.loads(res.content.decode('utf-8'))
        if resp_json["success"]:
            return resp_json["price"]
    return None


if __name__ == '__main__':
    print("Expected to trade at:" + str(get_price()))
    print("Effectively traded at:" + trade(TRADER_ID, 100, Side.BUY))