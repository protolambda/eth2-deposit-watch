from sqlalchemy import Column, Integer, ForeignKey, LargeBinary, BigInteger
from sqlalchemy.ext.declarative import declarative_base
Base = declarative_base()

BlockNumber = BigInteger
Eth1BlockHash = LargeBinary(length=32)

TxHash = LargeBinary(length=32)

BLSPubkey = LargeBinary(length=48)
BLSSignature = LargeBinary(length=96)

Bytes32 = LargeBinary(length=32)
Root = LargeBinary(length=32)
Gwei = BigInteger
Slot = BigInteger
ValidatorIndex = BigInteger


class CanonBlock(Base):
    __tablename__ = 'canon_block'
    block_num = Column(BlockNumber, primary_key=True)
    block_hash = Column(Eth1BlockHash, ForeignKey('eth1_block.block_hash'))


class Eth1Block(Base):
    __tablename__ = 'eth1_block'
    block_hash = Column(Eth1BlockHash, primary_key=True)
    parent_hash = Column(Eth1BlockHash, ForeignKey('eth1_block.block_hash'), nullable=True)

    block_num = Column(BlockNumber)
    timestamp = Column(Integer)


class Eth1Data(Base):
    __tablename__ = 'eth1_data'
    data_root = Column(Root, primary_key=True)
    deposit_root = Column(Root)
    deposit_count = Column(Integer)
    block_hash = Column(Eth1BlockHash)


class Eth1BlockVote(Base):
    __tablename__ = 'eth1_block_vote'
    beacon_block_root = Column(Root, ForeignKey('beacon_block.block_root'), primary_key=True)
    slot = Column(Slot)
    voting_period_slot = Column(Slot, ForeignKey('eth1_voting_period.start_slot'))
    eth1_data = Column(Root, ForeignKey('eth1_data.data_root'))
    proposer_index = Column(ValidatorIndex)


class DepositTx(Base):
    __tablename__ = 'deposit_tx'
    block_hash = Column(Eth1BlockHash, ForeignKey('eth1_block.block_hash'))
    tx_index = Column(Integer)
    tx_hash = Column(TxHash, primary_key=True)
    pubkey = Column(BLSPubkey)
    withdrawal_credentials = Column(Bytes32)
    amount = Column(Gwei)
    signature = Column(BLSSignature)


class Eth1VotingPeriod(Base):
    __tablename__ = 'eth1_voting_period'
    start_block_root = Column(Root, primary_key=True)
    start_slot = Column(Slot)
    current_data = Column(Root, ForeignKey('eth1_data.data_root'))


class Validator(Base):
    __tablename__ = 'validator'
    intro_block_root = Column(Root, primary_key=True)
    pubkey = Column(BLSPubkey, primary_key=True)
    # the root of the beacon block when the validator was created in the beacon state
    validator_index = Column(ValidatorIndex)
    withdrawal_credentials = Column(Bytes32)


class BeaconBlock(Base):
    __tablename__ = 'beacon_block'
    block_root = Column(Root, primary_key=True)
    slot = Column(Slot)
    state_root = Column(Root, ForeignKey('beacon_state.state_root'))


class BeaconState(Base):
    __tablename__ = 'beacon_state'
    # Post state root, as referenced in the beacon block
    state_root = Column(Root, primary_key=True)
    slot = Column(Slot)
    current_data = Column(Root, ForeignKey('eth1_data.data_root'))


class CanonBeaconBlock(Base):
    __tablename__ = 'canon_beacon_block'
    slot = Column(Slot, primary_key=True)
    block_root = Column(Root, ForeignKey('beacon_block.block_root'))
