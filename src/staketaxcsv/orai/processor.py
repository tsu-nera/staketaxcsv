import logging
import pprint

import staketaxcsv.orai.constants as co
import staketaxcsv.common.ibc.handle
import staketaxcsv.common.ibc.processor
from staketaxcsv.orai.config_orai import localconfig
from staketaxcsv.settings_csv import ORAI_NODE  
from staketaxcsv.common.ibc.api_lcd_cosmwasm import CosmWasmLcdAPI
from staketaxcsv.common.ibc.MsgInfoIBC import MsgInfoIBC
from staketaxcsv.common.ibc.denoms import amount_currency_from_raw
from staketaxcsv.common.make_tx import make_swap_tx, make_transfer_in_tx, make_transfer_out_tx

# Initialize contracts cache
if not hasattr(localconfig, 'contracts'):
    localconfig.contracts = {}

# Initialize token info cache
if not hasattr(localconfig, 'token_info'):
    with open('staketaxcsv/orai/tickers/token_lists/oraidex.json', 'r') as f:
        import json
        localconfig.token_info = json.load(f)

def get_token_info(denom):
    """Get token symbol and decimals from denom"""
    token_info = localconfig.token_info.get(denom, {})
    if not token_info:
        return denom, 6  # デフォルトのデシマルは6
    return token_info.get('symbol', denom), token_info.get('decimals', 6)

def calculate_amount(amount_raw, denom):
    """Calculate actual amount considering decimals"""
    _, decimals = get_token_info(denom)
    try:
        return float(amount_raw) / (10 ** decimals)
    except (ValueError, TypeError):
        return 0

def process_txs(wallet_address, elems, exporter):
    for elem in elems:
        process_tx(wallet_address, elem, exporter)

def _is_execute_contract(message):
    return message.get('@type', '').endswith('MsgExecuteContract')

def _is_send(message):
    return message.get('@type', '').endswith('MsgSend')

def process_tx(wallet_address, elem, exporter): 
    logging.info("Processing transaction element: %s", elem.get('txhash', ''))
    
    # Extract messages and events from transaction
    messages = elem.get('tx', {}).get('body', {}).get('messages', [])
    events = elem.get('events', [])
    logging.info("Found %d messages in transaction", len(messages))

    # Create txinfo
    txinfo = staketaxcsv.common.ibc.processor.txinfo(
        wallet_address, elem, co.MINTSCAN_LABEL_ORAI, ORAI_NODE)
    
    # Add debug logging
    logging.info("TxInfo details: hash=%s, timestamp=%s", txinfo.txid, txinfo.timestamp)
    
    # txinfo.url = "https://scan.orai.io/txs/{}".format(txinfo.txid)
    txinfo.url = "https://scanium.io/Oraichain/tx/{}".format(txinfo.txid)

    if txinfo.is_failed:
        logging.info("Transaction failed, handling as failed transaction")
        staketaxcsv.common.ibc.processor.handle_failed_transaction(exporter, txinfo)
        return txinfo

    # Process each message
    for i, message in enumerate(messages):
        logging.info("Processing message %d: type=%s", i, message.get('@type', 'unknown'))

        if _is_execute_contract(message):
            _handle_execute_contract(exporter, txinfo, message, events)
        elif _is_send(message):
            _handle_send(exporter, txinfo, message, wallet_address)
        else:
            # Create MsgInfoIBC for other message types
            log = {'events': events, 'msg_index': i}
            msginfo = MsgInfoIBC(wallet_address, i, message, log, ORAI_NODE)
            staketaxcsv.common.ibc.handle.handle_unknown_detect_transfers(exporter, txinfo, msginfo)

    return txinfo

def _handle_send(exporter, txinfo, message, wallet_address):
    """Handle MsgSend transaction"""
    from_address = message.get('from_address')
    to_address = message.get('to_address')
    amount = message.get('amount', [])

    for coin in amount:
        amount_raw = coin.get('amount', '0')
        denom = coin.get('denom', 'orai')
        amount_value, currency = _parse_amount_currency(amount_raw, denom)

        if from_address == wallet_address:
            # Transfer out
            row = make_transfer_out_tx(txinfo, amount_value, currency)
            row.comment = f"Transfer to {to_address}"
            exporter.ingest_row(row)
        elif to_address == wallet_address:
            # Transfer in
            row = make_transfer_in_tx(txinfo, amount_value, currency)
            row.comment = f"Transfer from {from_address}"
            exporter.ingest_row(row)

def _parse_amount_currency(amount_raw, denom_raw):
    """Parse amount and currency from raw strings"""
    if not amount_raw or not denom_raw:
        return 0, denom_raw
    
    # Get symbol from denom
    symbol, decimals = get_token_info(denom_raw)
    try:
        amount = float(amount_raw) / (10 ** decimals)
    except (ValueError, TypeError):
        amount = 0
    return amount, symbol

def _handle_oraidex_swap(exporter, txinfo, message, events):
    """Handle OraiDEX swap transaction"""
    msg = message.get('msg', {})
    
    # Check for swap_and_action
    if 'swap_and_action' in msg:
        swap_info = msg.get('swap_and_action', {})

        input_denom = message.get('funds')[0].get('denom')
        input_amount = message.get('funds')[0].get('amount')
        output_denom = swap_info.get('min_asset').get('native').get('denom')

        operations = swap_info.get('user_swap', {}).get('swap_exact_asset_in', {}).get('operations', [])
        
        for event in events:
            if event.get('type') == 'wasm':
                attrs = {attr['key']: attr['value'] for attr in event.get('attributes', [])}
                
                # Get output amount from last operation
                if ('post_swap_action_amount_out' in attrs):
                    output_amount = attrs.get('post_swap_action_amount_out')

        if input_amount and output_amount:
            input_amount, input_currency = _parse_amount_currency(input_amount, input_denom)
            output_amount, output_currency = _parse_amount_currency(output_amount, output_denom)
            
            if input_amount > 0 and output_amount > 0:
                row = make_swap_tx(txinfo, input_amount, input_currency, output_amount, output_currency)
                row.comment = "OraiDEX Swap from " + input_currency + " to " + output_currency
                exporter.ingest_row(row)

def _is_bridge_contract(message):
    """Check if the message is a bridge contract execution"""
    msg = message.get('msg', {})
    return 'add_tx' in msg and msg.get('add_tx', {}).get('value', {}).get('tx_type') == 'deposit'

def _get_factory_token_from_events(events, remote_denom):
    """Get factory token denom from events"""
    for event in reversed(events):
        if event.get('type') == 'coin_received':
            for attr in event.get('attributes', []):
                if attr.get('key') == 'amount' and remote_denom in attr.get('value', ''):
                    # Extract factory token denom from the amount value
                    # Format: "1201739220factory/orai1.../So111..."
                    amount_str = attr.get('value', '')
                    parts = amount_str.split('factory/')
                    if len(parts) > 1:
                        return 'factory/' + parts[1].split(remote_denom)[0] + remote_denom
    return None

def _handle_bridge(exporter, txinfo, message, events):
    """Handle bridge transaction"""
    msg = message.get('msg', {})
    tx_value = msg.get('add_tx', {}).get('value', {})

    # Get transaction details
    remote_denom = tx_value.get('remote_denom', '')  # Original token denom
    # receiver = tx_value.get('receiver', '')
    # fee_receiver = tx_value.get('fee_receiver', '')
    
    # Get factory token denom from events
    # factory_denom = _get_factory_token_from_events(events, remote_denom)
    factory_denom = "orai" if  remote_denom == "oraiyuR7hz6h7ApC56mb52CJjPZBB34USTjzaELoaPk" else "factory/orai1wuvhex9xqs3r539mvc6mtm7n20fcj3qr2m0y9khx6n5vtlngfzes3k0rq9/" + remote_denom
    if not factory_denom:
        logging.warning(f"Could not find factory token for {remote_denom}, using remote_denom instead")
        factory_denom = remote_denom

    symbol, decimals = get_token_info(factory_denom)
    
    total_amount = float(tx_value.get('amount', '0')) / (10 ** decimals)
    # fee_amount = _parse_amount_currency(tx_value.get('fee_amount', '0'), "orai")

    # Create received amount row (total amount)
    row = make_transfer_in_tx(txinfo, total_amount, symbol)
    row.comment = f"Bridge deposit from {remote_denom}"
    exporter.ingest_row(row)

def _handle_execute_contract(exporter, txinfo, message, events):
    try:
        if _is_oraidex_swap(message):
            _handle_oraidex_swap(exporter, txinfo, message, events)
            return
        elif _is_bridge_contract(message):
            _handle_bridge(exporter, txinfo, message, events)
            return

        # Create MsgInfoIBC for other contract types
        log = {'events': events, 'msg_index': 0}
        msginfo = MsgInfoIBC(message.get('sender'), 0, message, log, ORAI_NODE)
        staketaxcsv.common.ibc.handle.handle_unknown_detect_transfers(exporter, txinfo, msginfo)
    except Exception as e:
        logging.error("Exception when handling txid=%s, exception=%s", txinfo.txid, str(e))
        log = {'events': events, 'msg_index': 0}
        msginfo = MsgInfoIBC(message.get('sender'), 0, message, log, ORAI_NODE)
        staketaxcsv.common.ibc.handle.handle_unknown_detect_transfers(exporter, txinfo, msginfo)

def _is_oraidex_swap(message):
    """Check if the message is an OraiDEX swap"""
    msg = str(message.get('msg', {}))
    return any(keyword in msg for keyword in [
        'execute_swap_operations',
        'swap_and_action',
        'swap_exact_asset_in',
        'swap'
    ])

