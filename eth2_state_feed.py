import trio
from typing import Optional
from itertools import zip_longest
from depwatch.models import Base, Eth1Data, Fork, Checkpoint, BeaconState, Validator, ValidatorStatus
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from eth2spec.phase0 import spec

engine = create_engine('sqlite:///foo.db')

Base.metadata.create_all(engine, checkfirst=True)

Session = sessionmaker(bind=engine)
session = Session()


def store_state(state: spec.BeaconState):
    state_root = state.hash_tree_root()
    eth1_data = state.eth1_data
    eth1_data_root = eth1_data.hash_tree_root()
    session.merge(Eth1Data(
        data_root=eth1_data_root,
        deposit_root=eth1_data.deposit_root,
        deposit_count=eth1_data.deposit_count,
        block_hash=eth1_data.block_hash,
    ))
    fork = state.fork
    session.merge(Fork(
        current_version=fork.current_version,
        previous_version=fork.previous_version,
        epoch=fork.epoch,
    ))

    prev_just_ch = state.previous_justified_checkpoint
    prev_just_ch_root = prev_just_ch.hash_tree_root()
    session.merge(Checkpoint(
        checkpoint_root=prev_just_ch_root,
        epoch=prev_just_ch.epoch,
        block_root=prev_just_ch.root,
    ))
    curr_just_ch = state.current_justified_checkpoint
    curr_just_ch_root = curr_just_ch.hash_tree_root()
    session.merge(Checkpoint(
        checkpoint_root=curr_just_ch_root,
        epoch=curr_just_ch.epoch,
        block_root=curr_just_ch.root,
    ))
    finalized_ch = state.finalized_checkpoint
    finalized_ch_root = finalized_ch.hash_tree_root()
    session.merge(Checkpoint(
        checkpoint_root=finalized_ch_root,
        epoch=finalized_ch.epoch,
        block_root=finalized_ch.root,
    ))

    header = state.latest_block_header.copy()
    header.state_root = state_root
    header_root = header.hash_tree_root()
    session.merge(BeaconState(
        state_root=state_root,
        latest_block_root=header_root,
        slot=state.slot,
        eth1_data=eth1_data_root,
        fork=fork.current_version,
        validators_root=state.validators.hash_tree_root(),
        balances=state.hash_tree_root(),
        total_slashings=spec.Gwei(sum(state.slashings.readonly_iter())),
        prev_epoch_att_count=len(state.previous_epoch_attestations),
        curr_epoch_atte_count=len(state.current_epoch_attestations),
        justification_bits=''.join('1' if state.justification_bits[i] else '0' for i in range(spec.JUSTIFICATION_BITS_LENGTH)),
        prev_just_checkpoint=prev_just_ch_root,
        curr_just_checkpoint=curr_just_ch_root,
        finalized_checkpoint=finalized_ch_root,
    ))


def store_validator_diff(prev_state: spec.BeaconState, curr_state: spec.BeaconState):
    # TODO store balance changes
    if prev_state.validators.hash_tree_root() == curr_state.validators.hash_tree_root():
        # Nothing more to do, registry did not change
        return
    prev: Optional[spec.Validator]
    curr: Optional[spec.Validator]

    header = curr_state.latest_block_header.copy()
    header.state_root = curr_state.hash_tree_root()
    block_root = header.hash_tree_root()
    slot = curr_state.slot

    for i, (prev, curr) in enumerate(zip_longest(prev_state.validators.readonly_iter(), curr_state.validators.readonly_iter())):
        assert curr is not None
        if prev is None:
            # Create new validator
            session.merge(Validator(
                intro_block_root=block_root,
                validator_index=i,
                intro_slot=slot,
                pubkey=curr.pubkey,
                withdrawal_credentials=curr.withdrawal_credentials,
            ))
        if prev is None or prev != curr:
            # Update validator status if it's a new or changed validator
            session.merge(ValidatorStatus(
                intro_block_root=block_root,
                validator_index=i,
                intro_slot=slot,
                effective_balance=curr.effective_balance,
                slashed=bool(curr.slashed),
                activation_eligibility_epoch=curr.activation_eligibility_epoch,
                activation_epoch=curr.activation_epoch,
                exit_epoch=curr.exit_epoch,
                withdrawable_epoch=curr.withdrawable_epoch,
            ))


async def ev_state_loop(recv: trio.MemoryReceiveChannel):
    prev_state: spec.BeaconState
    state: spec.BeaconState
    async for (prev_state, curr_state) in recv:
        store_state(curr_state)
        store_validator_diff(prev_state, curr_state)
        session.commit()


class APIState(spec.Container):
    root: spec.Root
    state: spec.BeaconState

# TODO: fetch states for every slot and block, and cache them


async def main():
    async with trio.open_nursery() as nursery:
        send, recv = trio.open_memory_channel(max_buffer_size=100)

        # TODO: find latest finalized state in DB, get head block, start backfill from head to fin.
        # nursery.start_soon(backfill_state, more_args, send)
        # TODO: start watching for new data, starting from head.
        # nursery.start_soon(watch_state, more_args, send)
        nursery.start_soon(ev_state_loop, recv)


if __name__ == '__main__':
    trio.run(main)
