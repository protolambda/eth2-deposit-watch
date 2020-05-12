from typing import Any, Dict, NamedTuple, Tuple, Union, Optional

from eth_typing import Address, BlockNumber, Hash32
from eth_utils import encode_hex, event_abi_to_log_topic

from web3 import Web3
from web3.eth import Contract
from web3._utils.filters import LogFilter
from web3.types import BlockIdentifier

import trio
from eth2spec.phase0.spec import DepositData, BLSPubkey, BLSSignature, Gwei, uint64, Bytes32


class Timestamp(uint64):
    pass


class Eth1Block(NamedTuple):
    block_hash: Hash32
    number: BlockNumber
    timestamp: Timestamp


class DepositLog(NamedTuple):
    block_number: BlockNumber
    block_hash: Hash32
    tx_index: int
    tx_hash: Hash32
    pubkey: BLSPubkey
    withdrawal_credentials: Bytes32
    amount: Gwei
    signature: BLSSignature

    @staticmethod
    def from_contract_log_dict(log: Dict[Any, Any]) -> "DepositLog":
        log_args = log["args"]
        return DepositLog(
            block_number=log["blockNumber"],
            block_hash=log["blockHash"],
            tx_index=log["transactionIndex"],
            tx_hash=log["transactionHash"],
            pubkey=BLSPubkey(log_args["pubkey"]),
            withdrawal_credentials=Bytes32(log_args["withdrawal_credentials"]),
            amount=Gwei(int.from_bytes(log_args["amount"], "little")),
            signature=BLSSignature(log_args["signature"]),
        )

    def to_deposit_data(self) -> DepositData:
        return DepositData(
            pubkey=self.pubkey,
            withdrawal_credentials=self.withdrawal_credentials,
            amount=self.amount,
            signature=self.signature,
        )


class DepLogFilterSub(object):
    log_filt: Optional[LogFilter]
    _deposit_contract: Contract
    _block_num_start: BlockIdentifier
    _block_num_end: BlockIdentifier

    def __init__(self, dep_contract: Contract, start: BlockIdentifier, end: BlockIdentifier):
        self._deposit_contract = dep_contract
        self._block_num_start = start
        self._block_num_end = end

    async def __aenter__(self):
        self.log_filt = self._deposit_contract.events.DepositEvent().createFilter(
            fromBlock=self._block_num_start, toBlock=self._block_num_end)
        print(f"created filter: {self.log_filt.filter_id}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        print(f"removing old filter: {self.log_filt.filter_id}")
        self._deposit_contract.web3.eth.uninstallFilter(self.log_filt.filter_id)


class DepositMonitor(object):
    w3: Web3

    _deposit_contract: Contract
    _deposit_event_abi: Dict[str, Any]
    _deposit_event_topic: str

    def __init__(self, w3: Web3, deposit_contract_address: Address, deposit_contract_abi: Dict[str, Any]) -> None:
        self.w3 = w3
        self._deposit_contract = self.w3.eth.contract(
            address=deposit_contract_address, abi=deposit_contract_abi
        )
        self._deposit_event_abi = self._deposit_contract.events.DepositEvent._get_event_abi()
        self._deposit_event_topic = encode_hex(event_abi_to_log_topic(self._deposit_event_abi))

    def get_block(self, arg: Union[Hash32, int, str]) -> Eth1Block:
        block_dict = self.w3.eth.getBlock(arg)
        if block_dict is None:
            raise Exception("block not found")
        return Eth1Block(
            block_hash=Hash32(block_dict["hash"]),
            number=BlockNumber(block_dict["number"]),
            timestamp=Timestamp(block_dict["timestamp"]),
        )

    def get_logs(self, block_num_start: BlockNumber, block_num_end: BlockNumber) -> Tuple[DepositLog, ...]:
        logs = self.w3.eth.getLogs({
            "fromBlock": block_num_start,
            "toBlock": block_num_end,
            "address": self._deposit_contract.address,
            "topics": [self._deposit_event_topic],
        })
        dep_ev = self._deposit_contract.events.DepositEvent()
        processed_logs = tuple(dep_ev.processLog(log) for log in logs)
        parsed_logs = tuple(DepositLog.from_contract_log_dict(log) for log in processed_logs)
        return parsed_logs

    async def watch_logs(self, block_num_start: BlockNumber, dest: trio.MemorySendChannel,
                         poll_interval: float = 2.0):
        """
        Watches chain, starting from block_num_start, for deposit logs. It watches for pending transactions too.
        Once mined or changed, a second log will occur to update the eth1 block hash or other data.
        This function is long-running, and watching stops as soon as the async function is canceled.
        The underlying web3 filter is automatically uninstalled.

        :param block_num_start: Starting point.
        :param poll_interval: How often to poll the filter for new entries.
        :param dest: A Trio memory channel to send batches (lists) of DepositLog entries to.
        """
        async with DepLogFilterSub(self._deposit_contract, block_num_start, 'pending') as sub:
            while True:
                batch = sub.log_filt.get_new_entries()
                print(f"processing batch of {len(batch)} entries")
                parsed_batch = []
                for log in batch:
                    print(f"incoming log: {log}")
                    dep_log = DepositLog.from_contract_log_dict(log)
                    print(f"parsed entry: {dep_log}")
                    parsed_batch.append(dep_log)
                await dest.send(dep_log)
                await trio.sleep(poll_interval)

    async def backfill_logs(self, from_block: BlockNumber, to_block: BlockNumber,
                            dest: trio.MemorySendChannel, step_slowdown: float = 0.5,
                            step_block_count: int = 1024):
        curr_dep_count = 0
        # catch up
        for curr_block_num in range(from_block, to_block, step_block_count):
            next_block_num = min(curr_block_num + step_block_count, to_block)
            next_dep_count = self.get_deposit_count(BlockNumber(next_block_num))
            print(f"deposit count {next_dep_count} at block #{next_block_num}")
            if next_dep_count > curr_dep_count:
                logs = self.get_logs(BlockNumber(curr_block_num), BlockNumber(next_block_num))
                print(f"fetched {len(logs)} logs from block {curr_block_num} to {next_block_num}")
                await dest.send(logs)
            await trio.sleep(step_slowdown)

    def get_deposit_count(self, block_number: BlockNumber) -> int:
        deposit_count_bytes = self._deposit_contract.functions.get_deposit_count().call(block_identifier=block_number)
        return int.from_bytes(deposit_count_bytes, "little")

    def get_deposit_root(self, block_number: BlockNumber) -> Hash32:
        return self._deposit_contract.functions.get_deposit_root().call(block_identifier=block_number)

