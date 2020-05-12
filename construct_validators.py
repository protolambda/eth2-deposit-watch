from eth_typing import BlockNumber

from eth1_conn import eth1mon
from settings import DEPOSIT_CONTRACT_DEPLOY_BLOCK

current_block = eth1mon.get_block("latest")
print(f"current block #{current_block.number}\n{current_block}")

current_dep_count = eth1mon.get_deposit_count(current_block.number)
print(f"current deposit count: {current_dep_count}")

# TODO: adjust if safety is needed
TRUSTED_CONFIRM_DISTANCE = 1024

finalized_block_num = max(DEPOSIT_CONTRACT_DEPLOY_BLOCK, current_block.number - TRUSTED_CONFIRM_DISTANCE)

CATCH_UP_STEP_SIZE = 1024

finalized_dep_logs = []

curr_dep_count = 0
# catch up
for curr_block_num in range(DEPOSIT_CONTRACT_DEPLOY_BLOCK, finalized_block_num, CATCH_UP_STEP_SIZE):
    next_block_num = min(curr_block_num + CATCH_UP_STEP_SIZE, finalized_block_num)
    next_dep_count = eth1mon.get_deposit_count(BlockNumber(next_block_num))
    print(f"deposit count {next_dep_count} at block #{next_block_num}")
    if next_dep_count > curr_dep_count:
        logs = eth1mon.get_logs(BlockNumber(curr_block_num), BlockNumber(next_block_num))
        print(f"fetched {len(logs)} logs from block {curr_block_num} to {next_block_num}")
        finalized_dep_logs.extend(logs)

finalized_dep_datas = [dep_log.to_deposit_data() for dep_log in finalized_dep_logs]

print("\n-----\n".join(f"#{i}:\n{dat}" for i, dat in enumerate(finalized_dep_datas)))


from eth2spec.phase0.spec import *

import milagro_bls_binding as bls

deposit_data_list = List[DepositData, 2**DEPOSIT_CONTRACT_TREE_DEPTH](*finalized_dep_datas)

print(f"deposit datas root: {deposit_data_list.hash_tree_root().hex()}")


validators = List[Validator, VALIDATOR_REGISTRY_LIMIT]()
balances = []
pub2idx = {}

bad_signature_dep_indices = []
top_up_deposits = []  # (index, top up amount)

for dep_index, deposit_data in enumerate(deposit_data_list.readonly_iter()):
    pubkey = deposit_data.pubkey
    amount = deposit_data.amount
    if pubkey not in pub2idx:
        # Verify the deposit signature (proof of possession) which is not checked by the deposit contract
        deposit_message = DepositMessage(
            pubkey=deposit_data.pubkey,
            withdrawal_credentials=deposit_data.withdrawal_credentials,
            amount=deposit_data.amount,
        )
        domain = compute_domain(DOMAIN_DEPOSIT)  # Fork-agnostic domain since deposits are valid across forks
        signing_root = compute_signing_root(deposit_message, domain)
        # TODO: super slow
        if not bls.Verify(pubkey, signing_root, deposit_data.signature):
            bad_signature_dep_indices.append(dep_index)
            continue

        val_index = len(validators)
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
        pub2idx[pubkey] = val_index
    else:
        # Increase balance by deposit amount
        index = ValidatorIndex(pub2idx[pubkey])
        balances[index] += amount
        top_up_deposits.append((index, amount))

print("\n\n\n")

for i, val in enumerate(validators.readonly_iter()):
    print(f"Validator {i}, balance {balances[i]}:\n{val}")

print("\n\n\n")

print("-----------")
print(f"Got {len(bad_signature_dep_indices)} bad deposits")

for i in bad_signature_dep_indices:
    dep_data = deposit_data_list[i]
    print(f"BAD signature on deposit #{i}, tx: \n{finalized_dep_logs[i].tx_hash.hex()}")

print("-----------")
print(f"Got {len(top_up_deposits)} top up deposits")

for (i, amount) in top_up_deposits:
    dep_data = deposit_data_list[i]
    val_index = pub2idx[dep_data.pubkey]
    print(f"deposit #{i} topped up validator {val_index} by {amount} gwei")

print("------------")
print(f"validators set root: {validators.hash_tree_root().hex()}")
print("-----------")

print("done")
# TODO tree
