import trio
from typing import Sequence
from depwatch.eth1_conn import eth1mon
from depwatch.monitor import DepositLog
from depwatch.models import Base, DepositTx, DepositData
from depwatch.settings import DEPOSIT_CONTRACT_DEPLOY_BLOCK, BACKFILL_REPEAT_DISTANCE
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import func
from eth2spec.phase0 import spec

engine = create_engine('sqlite:///foo.db')

Base.metadata.create_all(engine, checkfirst=True)

Session = sessionmaker(bind=engine)
session = Session()


async def ev_batch_loop(recv: trio.MemoryReceiveChannel):
    ev_batch: Sequence[DepositLog]
    async for ev_batch in recv:
        print(ev_batch)
        for ev in ev_batch:
            data = spec.DepositData(
                pubkey=ev.pubkey,
                withdrawal_credentials=ev.withdrawal_credentials,
                amount=ev.amount,
                signature=ev.signature,
            )
            data_root = data.hash_tree_root()
            session.merge(DepositData(
                data_root=data_root,
                pubkey=ev.pubkey,
                withdrawal_credentials=ev.withdrawal_credentials,
                amount=ev.amount,
                signature=ev.signature,
            ))
            session.merge(DepositTx(
                block_hash=ev.block_hash,
                block_num=ev.block_number,
                tx_index=ev.tx_index,
                tx_hash=ev.tx_hash,
                data=data_root,
            ))
        session.commit()


async def main():
    async with trio.open_nursery() as nursery:
        send, recv = trio.open_memory_channel(max_buffer_size=100)

        # Look for latest existing block, then adjust starting point from there.
        start_block_num = DEPOSIT_CONTRACT_DEPLOY_BLOCK
        max_block_number_res = session.query(func.max(DepositTx.block_num)).first()[0]
        if max_block_number_res is not None:
            start_block_num = max(DEPOSIT_CONTRACT_DEPLOY_BLOCK, max_block_number_res - BACKFILL_REPEAT_DISTANCE)

        current_block_num = eth1mon.get_block('latest').number
        print(f"start at block {start_block_num}, backfill up to {current_block_num}")
        nursery.start_soon(eth1mon.backfill_logs, start_block_num, current_block_num, send)
        # nursery.start_soon(eth1mon.watch_logs, current_block_num, send)
        nursery.start_soon(ev_batch_loop, recv)


if __name__ == '__main__':
    trio.run(main)
