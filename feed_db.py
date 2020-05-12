import trio
from typing import Sequence
from depwatch.eth1_conn import eth1mon
from depwatch.monitor import DepositLog
from depwatch.models import Base, DepositTx
from depwatch.settings import DEPOSIT_CONTRACT_DEPLOY_BLOCK
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine('sqlite:///foo.db')

Base.metadata.create_all(engine, checkfirst=True)

Session = sessionmaker(bind=engine)
session = Session()


async def ev_batch_loop(recv: trio.MemoryReceiveChannel):
    ev_batch: Sequence[DepositLog]
    async for ev_batch in recv:
        print(ev_batch)
        session.add_all(DepositTx(
            block_hash=ev.block_hash,
            tx_index=ev.tx_index,
            tx_hash=ev.tx_hash,
            pubkey=ev.pubkey,
            withdrawal_credentials=ev.withdrawal_credentials,
            amount=ev.amount,
            signature=ev.signature,
        ) for ev in ev_batch)
        session.commit()


async def main():
    async with trio.open_nursery() as nursery:
        send, recv = trio.open_memory_channel(max_buffer_size=100)
        start_block_num = DEPOSIT_CONTRACT_DEPLOY_BLOCK
        current_block_num = eth1mon.get_block('latest').number
        print(f"start at block {start_block_num}, backfill up to {current_block_num}")
        nursery.start_soon(eth1mon.backfill_logs, start_block_num, current_block_num, send)
        # nursery.start_soon(eth1mon.watch_logs, current_block_num, send)
        nursery.start_soon(ev_batch_loop, recv)


if __name__ == '__main__':
    trio.run(main)
