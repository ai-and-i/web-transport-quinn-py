import asyncio

import pytest
import pytest_asyncio

import web_transport


@pytest_asyncio.fixture
async def session_pair(self_signed_cert, cert_hash):
    """Create a connected server/client session pair."""
    cert, key = self_signed_cert

    server = web_transport.Server(
        certificate_chain=[cert],
        private_key=key,
        bind="[::1]:0",
    )
    await server.__aenter__()
    _, port = server.local_addr

    client = web_transport.Client(server_certificate_hashes=[cert_hash])
    await client.__aenter__()

    # Connect
    async def accept():
        request = await server.accept()
        assert request is not None
        return await request.accept()

    server_session, client_session = await asyncio.gather(
        accept(),
        client.connect(f"https://[::1]:{port}"),
    )

    yield server_session, client_session

    client_session.close()
    server_session.close()
    await client.__aexit__(None, None, None)
    await server.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_write_some(session_pair):
    server_session, client_session = session_pair

    async def server_side():
        send, recv = await server_session.accept_bi()
        data = await recv.read()
        async with send:
            await send.write(data)

    server_task = asyncio.create_task(server_side())

    send, recv = await client_session.open_bi()
    n = await send.write_some(b"hello")
    assert isinstance(n, int)
    assert n > 0
    send.finish()

    response = await recv.read()
    assert response == b"hello"
    await server_task


@pytest.mark.asyncio
async def test_send_stream_context_manager_finish(session_pair):
    server_session, client_session = session_pair

    send, _recv = await client_session.open_bi()
    async with send:
        await send.write(b"test data")
    # After clean exit, stream should be finished (no exception)


@pytest.mark.asyncio
async def test_recv_stream_async_iteration(session_pair):
    server_session, client_session = session_pair

    async def server_side():
        send, recv = await server_session.accept_bi()
        chunks = []
        async for chunk in recv:
            chunks.append(chunk)
        async with send:
            await send.write(b"".join(chunks))

    send, recv = await client_session.open_bi()

    server_task = asyncio.create_task(server_side())

    async with send:
        await send.write(b"chunk1")
        await send.write(b"chunk2")

    response = await recv.read()
    assert response == b"chunk1chunk2"
    await server_task


@pytest.mark.asyncio
async def test_readexactly(session_pair):
    server_session, client_session = session_pair

    async def server_side():
        send, _recv = await server_session.accept_bi()
        async with send:
            await send.write(b"exactly10!")

    _send, recv = await client_session.open_bi()
    server_task = asyncio.create_task(server_side())

    data = await recv.readexactly(10)
    assert data == b"exactly10!"
    await server_task


@pytest.mark.asyncio
async def test_readexactly_incomplete(session_pair):
    server_session, client_session = session_pair

    async def server_side():
        send, _recv = await server_session.accept_bi()
        async with send:
            await send.write(b"short")

    _send, recv = await client_session.open_bi()
    server_task = asyncio.create_task(server_side())

    with pytest.raises(web_transport.StreamIncompleteReadError) as exc_info:
        await recv.readexactly(100)

    assert exc_info.value.expected == 100
    assert exc_info.value.partial == b"short"
    await server_task


@pytest.mark.asyncio
async def test_priority(session_pair):
    _server_session, client_session = session_pair

    send, _recv = await client_session.open_bi()
    # Default priority
    p = send.priority
    assert isinstance(p, int)

    send.priority = 42
    assert send.priority == 42
    send.finish()
