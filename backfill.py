import trio
from depwatch.eth1_conn import eth1mon
from depwatch.models import Base
from depwatch.settings import DEPOSIT_CONTRACT_DEPLOY_BLOCK
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine('sqlite:///foo.db')

Base.metadata.create_all(engine, checkfirst=True)

Session = sessionmaker(bind=engine)
session = Session()


async def ev_batch_loop(recv: trio.MemoryReceiveChannel):
    async for ev_batch in recv:
        print(ev_batch)


async def main():
    async with trio.open_nursery() as nursery:
        send, recv = trio.open_memory_channel(max_buffer_size=100)
        start_block_num = DEPOSIT_CONTRACT_DEPLOY_BLOCK
        current_block_num = eth1mon.get_block('latest').number
        nursery.start_soon(eth1mon.backfill_logs, start_block_num, current_block_num, send)
        nursery.start_soon(eth1mon.watch_logs, current_block_num, send)
        nursery.start_soon(ev_batch_loop, recv)


if __name__ == '__main__':
    trio.run(main)
