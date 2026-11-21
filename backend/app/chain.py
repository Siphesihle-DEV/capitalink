"""Avalanche Fuji adapter. Never raises into the ledger: failures are recorded in chain_txs and can be reconciled."""
import os, json
from web3 import Web3
from .db import ChainTx

SIGS = {  # must match SMEFinancingRegistry.sol
    "registerFinancing": ["bytes32", "uint256", "bytes32"],
    "recordAllocation": ["bytes32", "uint256", "bytes32"],
    "recordDisbursement": ["bytes32", "uint256", "bytes32"],
    "recordRepayment": ["bytes32", "uint256", "uint256", "uint256", "bytes32"],
    "recordDistribution": ["bytes32", "uint256", "bytes32"],
}
ABI = [{"type": "function", "name": n, "stateMutability": "nonpayable", "outputs": [],
        "inputs": [{"name": f"a{i}", "type": t} for i, t in enumerate(a)]} for n, a in SIGS.items()]
EXPLORER = "https://testnet.snowtrace.io/tx/"
h = lambda text: Web3.keccak(text=text)  # ids/refs go on-chain as hashes only, never personal data
cents = lambda d: int(d * 100)

def _conf():
    return os.getenv("RELAYER_PRIVATE_KEY"), os.getenv("REGISTRY_ADDRESS"), os.getenv("AVAX_RPC", "https://api.avax-test.network/ext/bc/C/rpc")

def record(s, fn, ref, *args):
    """Send one registry call. `ref` is the unique business key, used for idempotency."""
    key = f"{fn}:{ref}"
    if s.query(ChainTx).filter(ChainTx.ref == key, ChainTx.status.in_(["pending", "confirmed", "skipped"])).first():
        return
    pk, addr, rpc = _conf()
    row = ChainTx(event=fn, ref=key, status="skipped", note="Chain not configured (set RELAYER_PRIVATE_KEY and REGISTRY_ADDRESS)")
    try:
        if pk and addr:
            w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 20}))
            acct = w3.eth.account.from_key(pk)
            c = w3.eth.contract(address=Web3.to_checksum_address(addr), abi=ABI)
            tx = getattr(c.functions, fn)(*args).build_transaction({
                "from": acct.address, "nonce": w3.eth.get_transaction_count(acct.address, "pending"),
                "chainId": 43113})
            signed = acct.sign_transaction(tx)
            row.tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction).hex()
            row.status, row.note = "pending", "Fuji testnet transaction"
    except Exception as e:
        row.status, row.note = "failed", str(e)[:300]
    s.add(row)

def reconcile(s):
    pk, addr, rpc = _conf()
    if not pk: return 0
    w3 = Web3(Web3.HTTPProvider(rpc)); n = 0
    for r in s.query(ChainTx).filter(ChainTx.status == "pending"):
        try:
            rc = w3.eth.get_transaction_receipt(r.tx_hash)
            r.status = "confirmed" if rc.status == 1 else "failed"; r.block = rc.blockNumber; n += 1
        except Exception:
            pass  # still pending
    s.commit(); return n
