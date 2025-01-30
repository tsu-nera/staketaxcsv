"""
usage: python3 staketaxcsv/sol/tickers/gather/jupiter.py

* Writes tickers json file to staketaxcsv/sol/tickers/token_lists/jupiter.YYYYMMDD.json,
  which effectively updates the recognized token symbols for the solana report.

"""
import logging

import requests
import json
import os
from datetime import datetime

from staketaxcsv.orai.tickers.tickers import TOKEN_LISTS_DIR
ORAIDEX_TOKENS_LIST_API = "https://oraicommon.oraidex.io/api/v1/chains?dex=oraidex"

def fetch_oraidex_tokens():
    logging.info("Fetching %s ...", ORAIDEX_TOKENS_LIST_API)
    try:
        response = requests.get(ORAIDEX_TOKENS_LIST_API)
        response.raise_for_status()
        logging.info("Fetched.")
        return response.json()
    except requests.RequestException as e:
        print(f"Error fetching data from OraiDEX API: {e}")
        return None

# {
# "coinDenom": "SOL",
# "coinMinimalDenom": "factory/orai1wuvhex9xqs3r539mvc6mtm7n20fcj3qr2m0y9khx6n5vtlngfzes3k0rq9/So11111111111111111111111111111111111111112",
# "coinDecimals": 9,
# "bridgeTo": [
# "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"
# ],
# "coinGeckoId": "solana",
# "coinImageUrl": "https://assets.coingecko.com/coins/images/4128/standard/solana.png?1718769756"
# },
def save_tokens_to_file(data):
    data = data[0]['currencies']
    token_dict = {}
    for token in data:  
        token_dict[token['coinMinimalDenom']] = {
            'symbol': token['coinDenom'],
            'decimals': token['coinDecimals']            
        }
    # today = datetime.now().strftime("%Y%m%d")
    # filename = os.path.join(TOKEN_LISTS_DIR, f"oraidex.{today}.json")
    filename = os.path.join(TOKEN_LISTS_DIR, f"oraidex.json")

    with open(filename, 'w') as file:
        json.dump(token_dict, file, indent=4)

    logging.info("Wrote to %s", filename)


def main():
    tokens = fetch_oraidex_tokens()
    if tokens:
        save_tokens_to_file(tokens)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
