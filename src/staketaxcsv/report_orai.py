"""
usage: python3 report_orai.py <walletaddress> [--format all|cointracking|koinly|..]

Prints transactions and writes CSV(s) to _reports/ORAI*.csv
"""

import logging
import pprint

import staketaxcsv.orai.processor
from staketaxcsv.orai.config_orai import localconfig
from staketaxcsv.orai.progress_orai import SECONDS_PER_PAGE, ProgressOrai
from staketaxcsv.common import report_util
from staketaxcsv.common.Cache import Cache
from staketaxcsv.common.Exporter import Exporter
from staketaxcsv.settings_csv import ORAI_NODE, TICKER_ORAI
from staketaxcsv.common.ibc.tx_data import TxDataLcd

def main():
    report_util.main_default(TICKER_ORAI)

def read_options(options):
    report_util.read_common_options(localconfig, options)
    logging.info("localconfig: %s", localconfig.__dict__)

def _txdata():
    max_txs = localconfig.limit
    return TxDataLcd(ORAI_NODE, max_txs)


def wallet_exists(wallet_address):
    return _txdata().account_exists(wallet_address)


def txone(wallet_address, txid):
    elem = _txdata().get_tx(txid)
    exporter = Exporter(wallet_address, localconfig, TICKER_ORAI)

    txinfo = staketaxcsv.orai.processor.process_tx(wallet_address, elem, exporter)
    
    return exporter


def estimate_duration(wallet_address, options):
    max_txs = localconfig.limit
    return SECONDS_PER_PAGE * _txdata().get_txs_pages_count(wallet_address)


def txhistory(wallet_address):
    """ Configure localconfig based on options dictionary. """
    progress = ProgressOrai()
    exporter = Exporter(wallet_address, localconfig, TICKER_ORAI)
    txdata = _txdata()

    # Fetch count of transactions to estimate progress more accurately
    count_pages = txdata.get_txs_pages_count(wallet_address)
    progress.set_estimate(count_pages)

    # Fetch transactions
    elems = txdata.get_txs_all(wallet_address, progress)

    progress.report_message(f"Processing {len(elems)} transactions... ")
    staketaxcsv.orai.processor.process_txs(wallet_address, elems, exporter)

    return exporter


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
