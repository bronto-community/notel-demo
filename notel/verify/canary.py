import asyncio
import os
import sys

TCP_PORTS = [int(p) for p in os.environ.get(
    "CANARY_TCP_PORTS", "4317,4318,55680,55681,9411,14250,14268,9464,8889"
).split(",")]
UDP_PORTS = [int(p) for p in os.environ.get("CANARY_UDP_PORTS", "6831,6832").split(",")]


def report(proto, port, peer):
    print(f"CANARY_HIT proto={proto} port={port} peer={peer}", flush=True)


async def tcp_server(port):
    async def handle(reader, writer):
        report("tcp", port, writer.get_extra_info("peername"))
        writer.close()

    await asyncio.start_server(handle, "0.0.0.0", port)


class Udp(asyncio.DatagramProtocol):
    def __init__(self, port):
        self.port = port

    def datagram_received(self, data, addr):
        report("udp", self.port, addr)


async def main():
    loop = asyncio.get_running_loop()
    for port in TCP_PORTS:
        await tcp_server(port)
    for port in UDP_PORTS:
        await loop.create_datagram_endpoint(lambda p=port: Udp(p), local_addr=("0.0.0.0", port))
    print(f"canary listening tcp={TCP_PORTS} udp={UDP_PORTS}", flush=True)
    await asyncio.Event().wait()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
