import io
import json
from eth_typing import Address

from web3 import Web3
from web3.middleware import geth_poa_middleware  # For Goerli

from monitor import DepositMonitor

from settings import *

with io.open("deposit_abi.json", "r") as f:
    deposit_contract_json = f.read()

deposit_contract_abi = json.loads(deposit_contract_json)["abi"]


w3prov = Web3.HTTPProvider(ETH1_RPC) if ETH1_RPC.startswith("http") else Web3.WebsocketProvider(ETH1_RPC)
w3: Web3 = Web3(w3prov)

# Handle POA Goerli style "extraData" in Web3
# inject the poa compatibility middleware to the innermost layer
w3.middleware_onion.inject(geth_poa_middleware, layer=0)


contract_addr = Address(bytes.fromhex(DEPOSIT_CONTRACT_ADDRESS.replace("0x", "")))
eth1mon = DepositMonitor(w3, contract_addr, deposit_contract_abi)
