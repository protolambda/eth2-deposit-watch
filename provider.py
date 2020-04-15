from typing import Any, Dict, NamedTuple, Tuple, Union

from eth_typing import Address, BlockNumber, Hash32
from eth_utils import encode_hex, event_abi_to_log_topic

from web3 import Web3

from eth2spec.phase0.spec import DepositData, BLSPubkey, BLSSignature, Gwei, uint64, Bytes32


class Timestamp(uint64):
    pass


class Eth1Block(NamedTuple):
    block_hash: Hash32
    number: BlockNumber
    timestamp: Timestamp


class DepositLog(NamedTuple):
    block_hash: Hash32
    pubkey: BLSPubkey
    withdrawal_credentials: Bytes32
    amount: Gwei
    signature: BLSSignature

    @classmethod
    def from_contract_log_dict(cls, log: Dict[Any, Any]) -> "DepositLog":
        log_args = log["args"]
        return cls(
            block_hash=log["blockHash"],
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


class Web3Eth1DataProvider(object):
    w3: Web3

    _deposit_contract: "Web3.eth.contract"
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
        processed_logs = tuple(self._deposit_contract.events.DepositEvent().processLog(log) for log in logs)
        parsed_logs = tuple(DepositLog.from_contract_log_dict(log) for log in processed_logs)
        return parsed_logs

    def get_deposit_count(self, block_number: BlockNumber) -> int:
        deposit_count_bytes = self._deposit_contract.functions.get_deposit_count().call(block_identifier=block_number)
        return int.from_bytes(deposit_count_bytes, "little")

    def get_deposit_root(self, block_number: BlockNumber) -> Hash32:
        return self._deposit_contract.functions.get_deposit_root().call(block_identifier=block_number)

