import trio
from typing import Sequence
from depwatch.eth1_conn import eth1mon
from depwatch.monitor import EnhancedEth1Block
from depwatch.models import Base, Eth1Block
from depwatch.settings import DEPOSIT_CONTRACT_DEPLOY_BLOCK, BACKFILL_REPEAT_DISTANCE
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import func

engine = create_engine('sqlite:///foo.db')

Base.metadata.create_all(engine, checkfirst=True)

Session = sessionmaker(bind=engine)
session = Session()


async def ev_batch_loop(recv: trio.MemoryReceiveChannel):
    ev_batch: Sequence[EnhancedEth1Block]
    async for ev in recv:
        print(ev)
        session.merge(Eth1Block(
            block_hash=ev.eth1_block.block_hash,
            parent_hash=ev.eth1_block.parent_hash,
            block_num=ev.eth1_block.number,
            timestamp=ev.eth1_block.timestamp,
            deposit_count=ev.deposit_count,
        ))
        session.commit()


async def main():
    async with trio.open_nursery() as nursery:
        send, recv = trio.open_memory_channel(max_buffer_size=100)

        # Look for latest existing block, then adjust starting point from there.
        start_block_num = DEPOSIT_CONTRACT_DEPLOY_BLOCK
        max_block_number_res = session.query(func.max(Eth1Block.block_num)).first()[0]
        if max_block_number_res is not None:
            start_block_num = max(DEPOSIT_CONTRACT_DEPLOY_BLOCK, max_block_number_res - BACKFILL_REPEAT_DISTANCE)

        current_block_num = eth1mon.get_block('latest').number
        print(f"start at block {start_block_num}, backfill up to {current_block_num}")
        nursery.start_soon(eth1mon.backfill_blocks, start_block_num, current_block_num, send)
        # nursery.start_soon(eth1mon.watch_logs, current_block_num, send)
        nursery.start_soon(ev_batch_loop, recv)


# TODO: update CanonEth1Block as chain changes

if __name__ == '__main__':
    trio.run(main)
