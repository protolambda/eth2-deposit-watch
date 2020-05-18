import trio
from depwatch.models import (
    Base,
    BeaconBlock, SignedBeaconBlock,
    Eth1Data, Eth1BlockVote,
    ProposerSlashing, ProposerSlashingInclusion,
    AttesterSlashing, AttesterSlashingInclusion,
    AttestationData, IndexedAttestation, PendingAttestation,
    DepositData, Deposit, DepositInclusion,
    SignedVoluntaryExit, SignedVoluntaryExitInclusion,
    Checkpoint,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from eth2spec.phase0 import spec

engine = create_engine('sqlite:///foo.db')

Base.metadata.create_all(engine, checkfirst=True)

Session = sessionmaker(bind=engine)
session = Session()


def store_block(state: spec.BeaconState, signed_block: spec.SignedBeaconBlock):
    block = signed_block.message
    block_root = block.hash_tree_root()
    body = block.body

    # Eth1
    eth1_data = body.eth1_data
    eth1_data_root = eth1_data.hash_tree_root()
    session.merge(Eth1Data(
        data_root=eth1_data_root,
        deposit_root=eth1_data.deposit_root,
        deposit_count=eth1_data.deposit_count,
        block_hash=eth1_data.block_hash,
    ))
    session.merge(Eth1BlockVote(
        beacon_block_root=block_root,
        slot=block.slot,
        eth1_data=eth1_data_root,
        proposer_index=block.proposer_index,
    ))

    # Proposer slashings
    proposer_slashing: spec.ProposerSlashing
    for i, proposer_slashing in enumerate(body.proposer_slashings.readonly_iter()):
        session.merge(ProposerSlashing(
            root=proposer_slashing.hash_tree_root(),
            signed_header_1=proposer_slashing.signed_header_1.hash_tree_root(),
            signed_header_2=proposer_slashing.signed_header_2.hash_tree_root(),
        ))
        session.merge(ProposerSlashingInclusion(
            intro_block_root=block_root,
            intro_index=i,
            root=proposer_slashing.hash_tree_root(),
        ))

    # Attester slashings
    attester_slashing: spec.AttesterSlashing
    for i, attester_slashing in enumerate(body.attester_slashings.readonly_iter()):
        session.merge(AttesterSlashing(
            root=attester_slashing.hash_tree_root(),
            attestation_1=attester_slashing.attestation_1.hash_tree_root(),
            attestation_2=attester_slashing.attestation_2.hash_tree_root(),
        ))
        session.merge(AttesterSlashingInclusion(
            intro_block_root=block_root,
            intro_index=i,
            root=attester_slashing.hash_tree_root(),
        ))

    # Attestations
    attestation: spec.Attestation
    for i, attestation in enumerate(body.attestations.readonly_iter()):
        data = attestation.data
        source_ch = data.source
        source_ch_root = source_ch.hash_tree_root()
        session.merge(Checkpoint(
            checkpoint_root=source_ch_root,
            epoch=source_ch.epoch,
            block_root=source_ch.root,
        ))
        target_ch = data.target
        target_ch_root = target_ch.hash_tree_root()
        session.merge(Checkpoint(
            checkpoint_root=target_ch_root,
            epoch=target_ch.epoch,
            block_root=target_ch.root,
        ))
        data_root = data.hash_tree_root()
        session.merge(AttestationData(
            att_data_root=data_root,
            slot=data.slot,
            index=data.index,
            beacon_block_root=data.beacon_block_root,
            source=source_ch_root,
            target=target_ch_root,
        ))
        indexed = spec.get_indexed_attestation(state, attestation)
        indexed_att_root = indexed.hash_tree_root()
        session.merge(IndexedAttestation(
            indexed_attestation_root=indexed_att_root,
            normal_attestation_root=attestation.hash_tree_root(),
            attesting_indices=', '.join(map(str, indexed.attesting_indices.readonly_iter())),
            data=data_root,
            signature=indexed.signature,
        ))
        session.merge(PendingAttestation(
            intro_block_root=block_root,
            intro_index=i,
            indexed_att=indexed_att_root,
            inclusion_delay=block.slot - data.slot,
            proposer_index=block.proposer_index,
        ))

    # Deposits
    deposit: spec.Deposit
    for i, deposit in enumerate(body.deposits.readonly_iter()):
        data = deposit.data
        dep_data_root = data.hash_tree_root()
        session.merge(DepositData(
            data_root=dep_data_root,
            pubkey=data.pubkey,
            withdrawal_credentials=data.withdrawal_credentials,
            amount=data.amount,
            signature=data.signature,
        ))
        session.merge(Deposit(
            root=deposit.hash_tree_root(),
            deposit_index=state.eth1_deposit_index + i,
            dep_tree_root=state.eth1_data.deposit_root,
            data=dep_data_root,
        ))
        session.merge(DepositInclusion(
            intro_block_root=block_root,
            intro_index=i,
            root=deposit.hash_tree_root(),
        ))

    # Voluntary Exits
    sig_vol_exit: spec.SignedVoluntaryExit
    for i, sig_vol_exit in enumerate(body.voluntary_exits.readonly_iter()):
        session.merge(SignedVoluntaryExit(
            root=sig_vol_exit.hash_tree_root(),
            epoch=sig_vol_exit.message.epoch,
            validator_index=sig_vol_exit.message.validator_index,
            signature=sig_vol_exit.signature,
        ))
        session.merge(SignedVoluntaryExitInclusion(
            intro_block_root=block_root,
            intro_index=i,
            root=sig_vol_exit.hash_tree_root(),
        ))

    # The block itself
    session.merge(BeaconBlock(
        block_root=block_root,
        slot=block.slot,
        proposer_index=block.proposer_index,
        parent_root=block.parent_root,
        state_root=block.state_root,
        body_root=body.hash_tree_root(),
        randao_reveal=body.randao_reveal,
        graffiti=body.graffiti,
    ))

    # Block signature
    session.merge(SignedBeaconBlock(
        root=signed_block.hash_tree_root(),
        signature=signed_block.signature,
        block_root=block_root,
    ))


async def ev_block_loop(recv: trio.MemoryReceiveChannel):
    state: spec.BeaconState
    signed_block: spec.SignedBeaconBlock
    async for state, signed_block in recv:
        store_block(state, signed_block)
        session.commit()


class APISignedBlock(spec.Container):
    root: spec.Root
    state: spec.BeaconBlock

# TODO: fetch blocks and state for every slot and every fork, and cache them

# TODO: update CanonBeaconBlock as chain changes

async def main():
    async with trio.open_nursery() as nursery:
        send, recv = trio.open_memory_channel(max_buffer_size=100)

        # TODO: find latest finalized state in DB, get head block, start backfill from head to fin.
        # nursery.start_soon(backfill_state, more_args, send)
        # TODO: start watching for new data, starting from head.
        # nursery.start_soon(watch_state, more_args, send)
        nursery.start_soon(ev_block_loop, recv)


if __name__ == '__main__':
    trio.run(main)
