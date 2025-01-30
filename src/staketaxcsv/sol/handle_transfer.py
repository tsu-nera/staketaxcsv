import staketaxcsv.sol.util_sol
from staketaxcsv.common.make_tx import make_transfer_in_tx, make_transfer_out_tx
from staketaxcsv.sol.constants import CURRENCY_SOL, INSTRUCT_TRANSFERCHECK, INSTRUCT_TRANSFERCHECKED


def is_transfer(txinfo):
    instruction_types = txinfo.instruction_types
    log_instructions = txinfo.log_instructions

    # Check for transferCheck or transferChecked
    for instruction_type, program in instruction_types:
        if instruction_type in [INSTRUCT_TRANSFERCHECK, INSTRUCT_TRANSFERCHECKED]:
            return True

    if "Transfer" in log_instructions or ("transfer", "system") in instruction_types:
        # Verify no instructions except transfer or initialize/create/close account
        for instruction in log_instructions:
            if instruction not in ["Transfer", "InitializeAccount", "CloseAccount", "transfer", "system"]:
                return False
        return True

    return False

def is_spam_transfer(amount, currency):
    if currency == CURRENCY_SOL and float(amount) <= 0.0000001:
        return True
    return False

def handle_transfer(exporter, txinfo):
    txid = txinfo.txid
    transfers_in, transfers_out, _ = txinfo.transfers_net

    if len(transfers_out) == 1 and len(transfers_in) == 0:
        amount, currency, _, dest = transfers_out[0]

        # For SOL transfers, adjust fee from zero to non-zero if applicable
        if currency == CURRENCY_SOL and txinfo.fee == "" and txinfo.fee_blockchain > 0:
            txinfo.fee = txinfo.fee_blockchain
            amount -= txinfo.fee_blockchain

        row = make_transfer_out_tx(txinfo, amount, currency, dest)
        exporter.ingest_row(row)
    elif len(transfers_in) == 1 and len(transfers_out) == 0:
        amount, currency, _, _ = transfers_in[0]
        row = make_transfer_in_tx(txinfo, amount, currency)

        if is_spam_transfer(amount, currency):
            return  # スパムトランスファーの場合は処理を中止

        exporter.ingest_row(row)
    else:
        raise Exception(f"Bad condition in handle_transfer(), txid={txid}")
