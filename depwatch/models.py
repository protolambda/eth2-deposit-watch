from sqlalchemy import Column, Integer, ForeignKey, LargeBinary, BigInteger, Boolean, String
from sqlalchemy.ext.declarative import declarative_base
Base = declarative_base()

BlockNumber = BigInteger
Eth1BlockHash = LargeBinary(length=32)

TxHash = LargeBinary(length=32)

BLSPubkey = LargeBinary(length=48)
BLSSignature = LargeBinary(length=96)

Bytes32 = LargeBinary(length=32)
Root = LargeBinary(length=32)

Version = LargeBinary(length=4)

# It says BigInteger, but it's a SQL int64
Gwei = BigInteger
Slot = BigInteger
CommitteeIndex = BigInteger
DepositIndex = BigInteger
Epoch = BigInteger
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

    deposit_count = Column(Integer)


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


class DepositData(Base):
    __tablename__ = 'deposit_data'
    data_root = Column(Root, primary_key=True)
    pubkey = Column(BLSPubkey)
    withdrawal_credentials = Column(Bytes32)
    amount = Column(Gwei)
    signature = Column(BLSSignature)


class DepositTx(Base):
    __tablename__ = 'deposit_tx'
    block_hash = Column(Eth1BlockHash, ForeignKey('eth1_block.block_hash'))
    block_num = Column(Integer)
    tx_index = Column(Integer)
    tx_hash = Column(TxHash, primary_key=True)
    data = Column(Root, ForeignKey('deposit_data.data_root'))


class Eth1VotingPeriod(Base):
    __tablename__ = 'eth1_voting_period'
    start_block_root = Column(Root, primary_key=True)
    start_slot = Column(Slot)
    current_data = Column(Root, ForeignKey('eth1_data.data_root'))


class Validator(Base):
    __tablename__ = 'validator'
    # the root of the beacon block when the validator was created in the beacon state
    intro_block_root = Column(Root, primary_key=True)
    validator_index = Column(ValidatorIndex, primary_key=True)
    pubkey = Column(BLSPubkey)
    withdrawal_credentials = Column(Bytes32)


class ValidatorStatus(Base):
    __tablename__ = 'validator_status'
    intro_block_root = Column(Root, primary_key=True)
    validator_index = Column(ValidatorIndex, primary_key=True)
    slot = Column(Slot)
    effective_balance = Column(Gwei)
    slashed = Column(Boolean)
    activation_eligibility_epoch = Column(Epoch)
    activation_epoch = Column(Epoch)
    exit_epoch = Column(Epoch)
    withdrawable_epoch = Column(Epoch)


class BeaconBlock(Base):
    __tablename__ = 'beacon_block'
    block_root = Column(Root, primary_key=True)
    slot = Column(Slot)
    proposer_index = Column(ValidatorIndex)
    parent_root = Column(Root, ForeignKey('beacon_block.block_root'))
    state_root = Column(Root, ForeignKey('beacon_state.state_root'))
    body_root = Column(Root)


class BeaconState(Base):
    __tablename__ = 'beacon_state'
    # Post state root, as referenced in the beacon block
    state_root = Column(Root, primary_key=True)
    # like latest-block-header, except that the state-root is nicely up to date before hashing the latest header.
    latest_block_root = Column(Root, ForeignKey('beacon_block.block_root'))
    slot = Column(Slot)
    eth1_data = Column(Root, ForeignKey('eth1_data.data_root'))

    fork = Column(Version, ForeignKey('beacon_fork.current_version'))
    eth1_voting_period = Column(Root, ForeignKey('eth1_voting_period.start_block_root'))
    eth1_deposit_index = Column(DepositIndex)

    validators_root = Column(Root)
    balances = Column(Root)  # TODO index balance growth

    # sum of state.slashings (i.e. not total since genesis, but of last EPOCHS_PER_SLASHINGS_VECTOR epochs)
    total_slashings = Column(Gwei)

    # Attestations
    previous_epoch_attestations_count = Column(Integer)
    current_epoch_attestations_count = Column(Integer)

    # Finality
    justification_bits = Column(String)  # Bitvector[JUSTIFICATION_BITS_LENGTH], as literal bits, e.g. "1001"
    previous_justified_checkpoint = Column(Root, 'checkpoint.checkpoint_root')  # Previous epoch snapshot
    current_justified_checkpoint = Column(Root, 'checkpoint.checkpoint_root')
    finalized_checkpoint = Column(Root, 'checkpoint.checkpoint_root')


class CanonBeaconBlock(Base):
    __tablename__ = 'canon_beacon_block'
    slot = Column(Slot, primary_key=True)
    block_root = Column(Root, ForeignKey('beacon_block.block_root'))


class Fork(Base):
    __tablename__ = 'beacon_fork'
    current_version = Column(Version, primary_key=True)
    previous_version = Column(Version)
    epoch = Column(Epoch)


class ForkData(Base):
    __tablename__ = 'beacon_fork_data'
    current_version = Column(Version, primary_key=True)
    genesis_validators_root = Column(Root, primary_key=True)


class Checkpoint(Base):
    __tablename__ = 'checkpoint'
    checkpoint_root = Column(Root, primary_key=True)
    epoch = Column(Epoch)
    block_root = Column(Root)


class AttestationData(Base):
    __tablename__ = 'attestation_data'
    att_data_root = Column(Root, primary_key=True)
    slot = Column(Slot)
    index = Column(CommitteeIndex)
    # LMD GHOST vote
    beacon_block_root = Column(Root)
    # FFG vote
    source = Column(Root, 'checkpoint.checkpoint_root')
    target = Column(Root, 'checkpoint.checkpoint_root')


# TODO: improve how we represent participation in attestations

class IndexedAttestation(Base):
    __tablename__ = 'indexed_attestation'
    indexed_attestation_root = Column(Root, primary_key=True)
    normal_attestation_root = Column(Root)
    attesting_indices = Column(String)  # List[ValidatorIndex, MAX_VALIDATORS_PER_COMMITTEE]
    data = Column(Root, ForeignKey('attestation_data.att_data_root'))
    signature = Column(BLSSignature)


# PendingAttestation is essentially a "AttestationInclusion"
class PendingAttestation(Base):
    __tablename__ = 'pending_attestation'
    intro_block_root = Column(Root, primary_key=True)
    intro_index = Column(Integer, primary_key=True)
    indexed_att = Column(Root, ForeignKey('indexed_attestation.indexed_attestation_root'))
    inclusion_delay = Column(Slot)
    proposer_index = Column(ValidatorIndex)


class ProposerSlashing(Base):
    __tablename__ = 'proposer_slashing'
    root = Column(Root, primary_key=True)
    signed_header_1 = Column(BeaconBlock, ForeignKey('beacon_block.block_root'))
    signed_header_2 = Column(BeaconBlock, ForeignKey('beacon_block.block_root'))


class ProposerSlashingInclusion(Base):
    __tablename__ = 'proposer_slashing_inclusion'
    intro_block_root = Column(Root, primary_key=True)
    intro_index = Column(Integer, primary_key=True)
    root = Column(Root, ForeignKey('proposer_slashing.root'))


class AttesterSlashing(Base):
    __tablename__ = 'attester_slashing'
    root = Column(Root, primary_key=True)
    attestation_1 = Column(Root, ForeignKey('indexed_attestation.indexed_attestation_root'))
    attestation_2 = Column(Root, ForeignKey('indexed_attestation.indexed_attestation_root'))


class AttesterSlashingInclusion(Base):
    __tablename__ = 'attester_slashing_inclusion'
    intro_block_root = Column(Root, primary_key=True)
    intro_index = Column(Integer, primary_key=True)
    root = Column(Root, ForeignKey('attester_slashing.root'))


class Deposit(Base):
    __tablename__ = 'deposit'
    root = Column(Root, primary_key=True)
    deposit_index = Column(DepositIndex)
    dep_tree_root = Column(Root)
    # TODO not storing: proof = Column(String)  # Vector[Bytes32, DEPOSIT_CONTRACT_TREE_DEPTH + 1]
    data = Column(Root, 'deposit_data.data_root')


class DepositInclusion(Base):
    __tablename__ = 'deposit_inclusion'
    intro_block_root = Column(Root, primary_key=True)
    intro_index = Column(Integer, primary_key=True)
    root = Column(Root, ForeignKey('deposit.root'))


class SignedVoluntaryExit(Base):
    __tablename__ = 'vol_exit'
    root = Column(Root, primary_key=True)
    epoch = Column(Epoch)  # Earliest epoch when voluntary exit can be processed
    validator_index: ValidatorIndex
    signature = Column(BLSSignature)


class SignedVoluntaryExitInclusion(Base):
    __tablename__ = 'vol_exit_inclusion'
    intro_block_root = Column(Root, primary_key=True)
    intro_index = Column(Integer, primary_key=True)
    root = Column(Root, ForeignKey('vol_exit.root'))
