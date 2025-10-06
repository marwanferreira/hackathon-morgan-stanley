import requests
import pandas as pd
import time
from algo import  get_price

def stream_api_to_dataframe(interval=5):
    """
    Continuously fetch data from API and append rows to a DataFrame.
    
    Parameters:
        api_url (str): API endpoint.
        interval (int): Time (seconds) between requests.
    
    Returns:
        pd.DataFrame: Final DataFrame after manual stop (Ctrl+C).
    """
    df = pd.DataFrame()  # start empty
    
    try:
        while True:
            data = get_price()

            row = pd.DataFrame([data])

            # Append row
            df = pd.concat([df, row], ignore_index=True)

            print(f"Row added. Total rows: {len(df)}")
            # print(row)

            time.sleep(interval)  # wait before next fetch
    
    except KeyboardInterrupt:
        print("Stopped streaming.")
        return df
    
# Example with EURGBP price API
df = stream_api_to_dataframe(interval=2)
df.to_csv("EURGBP_prices.csv", index=False)  # Save to CSV