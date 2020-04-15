import io
import json

from web3 import Web3
from eth_typing import Address, BlockNumber

from provider import Web3Eth1DataProvider
from web3.middleware import geth_poa_middleware  # For Goerli

DEPOSIT_ABI_PATH = "deposit_abi.json"
ETH1_RPC = "https://goerli.infura.io/v3/caf2e67f3cec4926827e5b4d17dc5167"
DEPOSIT_CONTRACT_ADDRESS = Address(bytes.fromhex("0x5cA1e00004366Ac85f492887AAab12d0e6418876".replace("0x", "")))
DEPOSIT_CONTRACT_DEPLOY_BLOCK = 2523557

with io.open("deposit_abi.json", "r") as f:
    deposit_contract_json = f.read()

deposit_contract_abi = json.loads(deposit_contract_json)["abi"]


w3: Web3 = Web3(Web3.HTTPProvider(ETH1_RPC))
# Handle POA Goerli style "extraData" in Web3
# inject the poa compatibility middleware to the innermost layer
w3.middleware_onion.inject(geth_poa_middleware, layer=0)

provider = Web3Eth1DataProvider(w3, DEPOSIT_CONTRACT_ADDRESS, deposit_contract_abi)

current_block = provider.get_block("latest")
print(f"current block #{current_block.number}\n{current_block}")

current_dep_count = provider.get_deposit_count(current_block.number)
print(f"current deposit count: {current_dep_count}")

# TODO: adjust if safety is needed
TRUSTED_CONFIRM_DISTANCE = 0

finalized_num = max(DEPOSIT_CONTRACT_DEPLOY_BLOCK, current_block.number-TRUSTED_CONFIRM_DISTANCE)

CATCH_UP_STEP_SIZE = 1024

finalized_dep_logs = []

curr_dep_count = 0
# catch up
for curr_block_num in range(DEPOSIT_CONTRACT_DEPLOY_BLOCK, finalized_num, CATCH_UP_STEP_SIZE):
    next_block_num = min(curr_block_num+CATCH_UP_STEP_SIZE, finalized_num)
    next_dep_count = provider.get_deposit_count(BlockNumber(next_block_num))
    print(f"deposit count {next_dep_count} at block #{next_block_num}")
    if next_dep_count > curr_dep_count:
        logs = provider.get_logs(BlockNumber(curr_block_num), BlockNumber(next_block_num))
        print(f"fetched {len(logs)} logs from block {curr_block_num} to {next_block_num}")
        finalized_dep_logs.extend(logs)

finalized_dep_datas = [dep_log.to_deposit_data() for dep_log in finalized_dep_logs]

print("\n-----\n".join(f"#{i}:\n{dat}" for i, dat in enumerate(finalized_dep_datas)))


from eth2spec.phase0.spec import *

deposit_data_list = List[DepositData, 2**DEPOSIT_CONTRACT_TREE_DEPTH](*finalized_dep_datas)

print(f"deposit datas root: {deposit_data_list.hash_tree_root().hex()}")


validators = List[Validator, VALIDATOR_REGISTRY_LIMIT]()
balances = []
validator_pubkeys = []
pubkeys = set()

for index, deposit_data in enumerate(deposit_data_list.readonly_iter()):
    pubkey = deposit_data.pubkey
    amount = deposit_data.amount
    if pubkey not in validator_pubkeys:
        # Verify the deposit signature (proof of possession) which is not checked by the deposit contract
        deposit_message = DepositMessage(
            pubkey=deposit_data.pubkey,
            withdrawal_credentials=deposit_data.withdrawal_credentials,
            amount=deposit_data.amount,
        )
        domain = compute_domain(DOMAIN_DEPOSIT)  # Fork-agnostic domain since deposits are valid across forks
        signing_root = compute_signing_root(deposit_message, domain)
        # TODO: super slow
        # if not bls.Verify(pubkey, signing_root, deposit_data.signature):
        #     print(f"warning deposit {index} has a wrong signature")
        #     continue

        # Add validator and balance entries
        validators.append(Validator(
            pubkey=pubkey,
            withdrawal_credentials=deposit_data.withdrawal_credentials,
            activation_eligibility_epoch=FAR_FUTURE_EPOCH,
            activation_epoch=FAR_FUTURE_EPOCH,
            exit_epoch=FAR_FUTURE_EPOCH,
            withdrawable_epoch=FAR_FUTURE_EPOCH,
            effective_balance=min(amount - amount % EFFECTIVE_BALANCE_INCREMENT, MAX_EFFECTIVE_BALANCE),
        ))
        balances.append(amount)
        pubkeys.add(pubkey)
    else:
        # Increase balance by deposit amount
        index = ValidatorIndex(validator_pubkeys.index(pubkey))
        balances[index] += amount

print("\n\n\n")

for i, val in enumerate(validators.readonly_iter()):
    print(f"Validator {i}, balance {balances[i]}:\n{val}")

print("\n\n\n")

print("------------")
print(f"validators set root: {validators.hash_tree_root().hex()}")
print("-----------")

print("done")
# TODO tree
