import trio
from eth1_conn import eth1mon


async def log_loop(recv: trio.MemoryReceiveChannel):
    async for ev in recv:
        print(ev)


async def main():
    async with trio.open_nursery() as nursery:
        send, recv = trio.open_memory_channel(max_buffer_size=100)
        nursery.start_soon(eth1mon.watch_logs, 'latest', 2, send)
        nursery.start_soon(log_loop, recv)

if __name__ == '__main__':
    trio.run(main)
