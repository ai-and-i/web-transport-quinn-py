import asyncio

import pytest

import web_transport


@pytest.mark.asyncio
async def test_datagram_roundtrip(self_signed_cert, cert_hash):
    cert, key = self_signed_cert

    async with web_transport.Server(
        certificate_chain=[cert],
        private_key=key,
        bind="[::1]:0",
    ) as server:
        _, port = server.local_addr

        async def server_task():
            request = await server.accept()
            assert request is not None
            session = await request.accept()
            async with session:
                data = await session.receive_datagram()
                session.send_datagram(data)

        async def client_task():
            async with web_transport.Client(
                server_certificate_hashes=[cert_hash],
            ) as client:
                session = await client.connect(f"https://[::1]:{port}")
                async with session:
                    session.send_datagram(b"ping")
                    response = await session.receive_datagram()
                    assert response == b"ping"

        await asyncio.gather(
            asyncio.create_task(server_task()),
            asyncio.create_task(client_task()),
        )


@pytest.mark.asyncio
async def test_max_datagram_size(self_signed_cert, cert_hash):
    cert, key = self_signed_cert

    async with web_transport.Server(
        certificate_chain=[cert],
        private_key=key,
        bind="[::1]:0",
    ) as server:
        _, port = server.local_addr

        async def server_task():
            request = await server.accept()
            assert request is not None
            session = await request.accept()
            async with session:
                size = session.max_datagram_size
                assert isinstance(size, int)
                assert size > 0

        async def client_task():
            async with web_transport.Client(
                server_certificate_hashes=[cert_hash],
            ) as client:
                session = await client.connect(f"https://[::1]:{port}")
                async with session:
                    size = session.max_datagram_size
                    assert isinstance(size, int)
                    assert size > 0

        await asyncio.gather(
            asyncio.create_task(server_task()),
            asyncio.create_task(client_task()),
        )
