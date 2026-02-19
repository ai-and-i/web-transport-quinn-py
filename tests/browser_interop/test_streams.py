"""Browser interop tests for WebTransport bidi streams."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from .conftest import RunJS, ServerFactory

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_bidi_stream_echo(start_server: ServerFactory, run_js: RunJS) -> None:
    """UTF-8 text roundtrips through a bidi stream between Chromium and the server."""
    async with start_server() as (server, port, hash_b64):

        async def server_side() -> None:
            request = await server.accept()
            assert request is not None
            session = await request.accept()
            async with session:
                send, recv = await session.accept_bi()
                async with send:
                    data = await recv.read()
                    await send.write(data)

        async with asyncio.TaskGroup() as tg:
            tg.create_task(server_side())
            result = await run_js(
                port,
                hash_b64,
                """
                const stream = await transport.createBidirectionalStream();
                await writeAllString(stream.writable, "hello from chromium");
                return await readAllString(stream.readable);
            """,
            )

    assert result == "hello from chromium"


async def test_bidi_stream_binary_roundtrip(
    start_server: ServerFactory, run_js: RunJS
) -> None:
    """All 256 byte values survive the full browser-server-browser roundtrip."""
    async with start_server() as (server, port, hash_b64):

        async def server_side() -> None:
            request = await server.accept()
            assert request is not None
            session = await request.accept()
            async with session:
                send, recv = await session.accept_bi()
                async with send:
                    data = await recv.read()
                    await send.write(data)

        async with asyncio.TaskGroup() as tg:
            tg.create_task(server_side())
            result = await run_js(
                port,
                hash_b64,
                """
                const stream = await transport.createBidirectionalStream();
                // Send all 256 byte values
                const payload = new Uint8Array(256);
                for (let i = 0; i < 256; i++) payload[i] = i;
                await writeAll(stream.writable, payload);
                const echoed = await readAll(stream.readable);
                // Return as a regular array so it serializes to JSON
                return Array.from(echoed);
            """,
            )

    assert result == list(range(256))
