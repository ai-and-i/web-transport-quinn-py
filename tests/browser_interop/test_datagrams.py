"""Browser interop tests for WebTransport datagrams."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from .conftest import RunJS, ServerFactory

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_datagram_echo(start_server: ServerFactory, run_js: RunJS) -> None:
    """A datagram roundtrips between Chromium and the echo server."""
    async with start_server() as (server, port, hash_b64):

        async def server_side() -> None:
            request = await server.accept()
            assert request is not None
            session = await request.accept()
            async with session:
                dgram = await session.receive_datagram()
                session.send_datagram(dgram)

        async with asyncio.TaskGroup() as tg:
            tg.create_task(server_side())
            result = await run_js(
                port,
                hash_b64,
                """
                const writer = transport.datagrams.writable.getWriter();
                const reader = transport.datagrams.readable.getReader();
                const payload = new TextEncoder().encode("datagram ping");
                await writer.write(payload);
                const { value } = await reader.read();
                reader.releaseLock();
                writer.releaseLock();
                return new TextDecoder().decode(value);
            """,
            )

    assert result == "datagram ping"
