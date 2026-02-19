"""Browser interop tests for WebTransport connection lifecycle."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from .conftest import RunJS, ServerFactory

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_browser_connects_to_server(
    start_server: ServerFactory, run_js: RunJS
) -> None:
    """Chromium establishes a WebTransport session and transport.ready resolves."""
    async with start_server() as (server, port, hash_b64):

        async def server_side() -> None:
            request = await server.accept()
            assert request is not None
            session = await request.accept()
            async with session:
                await session.wait_closed()

        async with asyncio.TaskGroup() as tg:
            tg.create_task(server_side())
            result = await run_js(
                port,
                hash_b64,
                """
                // transport.ready already awaited by the harness — if we get
                // here, the connection succeeded.  Verify the expected API
                // surface exists.
                const api = {
                    createBidirectionalStream: typeof transport.createBidirectionalStream === "function",
                    createUnidirectionalStream: typeof transport.createUnidirectionalStream === "function",
                    datagrams: transport.datagrams !== undefined,
                    close: typeof transport.close === "function",
                    ready: transport.ready instanceof Promise,
                    closed: transport.closed instanceof Promise,
                };
                const missing = Object.entries(api)
                    .filter(([, v]) => !v).map(([k]) => k);
                if (missing.length > 0)
                    throw new Error("Missing API: " + missing.join(", "));
                return true;
            """,
            )

    assert result is True
