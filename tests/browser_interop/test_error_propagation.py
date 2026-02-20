"""Browser interop tests for cross-boundary error propagation."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import pytest

import web_transport
from .conftest import _webtransport_connect_js

if TYPE_CHECKING:
    from .conftest import RunJS, RunJSRaw, ServerFactory

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_server_close_during_browser_read(
    start_server: ServerFactory, run_js: RunJS
) -> None:
    """Server writes partial data, closes session → browser read sees error."""
    async with start_server() as (server, port, hash_b64):

        async def server_side() -> None:
            request = await server.accept()
            assert request is not None
            session = await request.accept()
            async with session:
                send, recv = await session.open_bi()
                await send.write(b"partial")
                # Small delay so browser accepts the stream before we close
                await asyncio.sleep(0.1)
                # Close session abruptly — don't finish the stream
                session.close(1, "abort")

        async with asyncio.TaskGroup() as tg:
            tg.create_task(server_side())
            result: Any = await run_js(
                port,
                hash_b64,
                """
                try {
                    const reader = transport.incomingBidirectionalStreams.getReader();
                    const { value: stream } = await reader.read();
                    reader.releaseLock();
                    const streamReader = stream.readable.getReader();
                    while (true) {
                        const { value, done } = await streamReader.read();
                        if (done) break;
                    }
                    return { errored: false };
                } catch (e) {
                    return { errored: true, message: e.toString() };
                }
            """,
            )

    assert isinstance(result, dict)
    assert result["errored"] is True


async def test_browser_close_during_server_read(
    start_server: ServerFactory, run_js: RunJS
) -> None:
    """Browser writes partial, closes transport → server recv.read() raises SessionClosedByPeer."""
    async with start_server() as (server, port, hash_b64):
        error: BaseException | None = None

        async def server_side() -> None:
            nonlocal error
            request = await server.accept()
            assert request is not None
            session = await request.accept()
            async with session:
                try:
                    send, recv = await session.accept_bi()
                    async with send:
                        # Try to read — browser will close mid-way
                        await recv.read()
                except (
                    web_transport.SessionClosedByPeer,
                    web_transport.SessionClosedLocally,
                    web_transport.StreamClosedByPeer,
                ) as e:
                    error = e

        async with asyncio.TaskGroup() as tg:
            tg.create_task(server_side())
            await run_js(
                port,
                hash_b64,
                """
                const stream = await transport.createBidirectionalStream();
                const writer = stream.writable.getWriter();
                await writer.write(new TextEncoder().encode("partial"));
                // Close transport abruptly (don't close the writer first)
                transport.close({closeCode: 1, reason: "abort"});
                return true;
            """,
            )

    assert error is not None


async def test_browser_close_during_server_write(
    start_server: ServerFactory, run_js: RunJS
) -> None:
    """Browser closes while server writes large data → server write raises."""
    async with start_server() as (server, port, hash_b64):
        error: BaseException | None = None

        async def server_side() -> None:
            nonlocal error
            request = await server.accept()
            assert request is not None
            session = await request.accept()
            async with session:
                send, recv = await session.accept_bi()
                try:
                    # Write a lot of data — browser will close mid-way
                    for _ in range(100):
                        await send.write(b"x" * 65536)
                except (
                    web_transport.SessionClosedByPeer,
                    web_transport.StreamClosedByPeer,
                    web_transport.SessionClosed,
                    web_transport.StreamClosed,
                ) as e:
                    error = e

        async with asyncio.TaskGroup() as tg:
            tg.create_task(server_side())
            await run_js(
                port,
                hash_b64,
                """
                const stream = await transport.createBidirectionalStream();
                // Give server a moment to start writing
                await new Promise(r => setTimeout(r, 100));
                transport.close({closeCode: 1, reason: "abort"});
                return true;
            """,
            )

    assert error is not None


async def test_open_bi_after_session_close_raises(
    start_server: ServerFactory, run_js: RunJS
) -> None:
    """session.close() then open_bi() raises SessionClosedLocally."""
    async with start_server() as (server, port, hash_b64):
        error: BaseException | None = None

        async def server_side() -> None:
            nonlocal error
            request = await server.accept()
            assert request is not None
            session = await request.accept()
            async with session:
                session.close()
                try:
                    await session.open_bi()
                except web_transport.SessionClosedLocally as e:
                    error = e

        async with asyncio.TaskGroup() as tg:
            tg.create_task(server_side())
            try:
                await run_js(port, hash_b64, "return true;")
            except Exception:
                pass

    assert isinstance(error, web_transport.SessionClosedLocally)


async def test_accept_bi_after_browser_close_raises(
    start_server: ServerFactory, run_js: RunJS
) -> None:
    """Browser closes → pending accept_bi() raises SessionClosed."""
    async with start_server() as (server, port, hash_b64):
        error: BaseException | None = None

        async def server_side() -> None:
            nonlocal error
            request = await server.accept()
            assert request is not None
            session = await request.accept()
            try:
                await session.accept_bi()
            except web_transport.SessionClosed as e:
                error = e

        async with asyncio.TaskGroup() as tg:
            tg.create_task(server_side())
            await run_js(
                port,
                hash_b64,
                """
                transport.close({closeCode: 0, reason: ""});
                return true;
            """,
            )

    assert isinstance(error, web_transport.SessionClosed)


async def test_send_datagram_after_close_raises(
    start_server: ServerFactory, run_js: RunJS
) -> None:
    """session.close() then send_datagram() raises SessionClosed."""
    async with start_server() as (server, port, hash_b64):
        error: BaseException | None = None

        async def server_side() -> None:
            nonlocal error
            request = await server.accept()
            assert request is not None
            session = await request.accept()
            async with session:
                session.close()
                try:
                    session.send_datagram(b"too late")
                except web_transport.SessionClosed as e:
                    error = e

        async with asyncio.TaskGroup() as tg:
            tg.create_task(server_side())
            try:
                await run_js(port, hash_b64, "return true;")
            except Exception:
                pass

    assert isinstance(error, web_transport.SessionClosed)


async def test_receive_datagram_after_browser_close_raises(
    start_server: ServerFactory, run_js: RunJS
) -> None:
    """Browser closes → pending receive_datagram() raises SessionClosed."""
    async with start_server() as (server, port, hash_b64):
        error: BaseException | None = None

        async def server_side() -> None:
            nonlocal error
            request = await server.accept()
            assert request is not None
            session = await request.accept()
            try:
                await session.receive_datagram()
            except web_transport.SessionClosed as e:
                error = e

        async with asyncio.TaskGroup() as tg:
            tg.create_task(server_side())
            await run_js(
                port,
                hash_b64,
                """
                transport.close({closeCode: 0, reason: ""});
                return true;
            """,
            )

    assert isinstance(error, web_transport.SessionClosed)


@pytest.mark.xfail(
    reason="Timing-sensitive: idle timeout interaction with Chromium's own timeout may cause flakiness"
)
async def test_idle_timeout_expires(
    start_server: ServerFactory, run_js_raw: RunJSRaw
) -> None:
    """Server max_idle_timeout=1, no keep-alive, idle 2s → server sees SessionTimeout."""
    async with start_server(max_idle_timeout=1, keep_alive_interval=None) as (
        server,
        port,
        hash_b64,
    ):
        close_reason: web_transport.SessionError | None = None

        async def server_side() -> None:
            nonlocal close_reason
            request = await server.accept()
            assert request is not None
            session = await request.accept()
            async with session:
                await session.wait_closed()
                close_reason = session.close_reason

        setup = _webtransport_connect_js(port, hash_b64)
        async with asyncio.TaskGroup() as tg:
            tg.create_task(server_side())
            await run_js_raw(f"""
                {setup}
                const transport = new WebTransport(url, transportOptions);
                await transport.ready;
                // Idle for 2 seconds
                await new Promise(r => setTimeout(r, 2000));
                try {{ transport.close(); }} catch (e) {{}}
                return true;
            """)

    assert isinstance(close_reason, web_transport.SessionTimeout)


async def test_keep_alive_prevents_timeout(
    start_server: ServerFactory, run_js_raw: RunJSRaw
) -> None:
    """Server max_idle_timeout=2, keep_alive_interval=0.5, idle 3s → session survives."""
    async with start_server(max_idle_timeout=2, keep_alive_interval=0.5) as (
        server,
        port,
        hash_b64,
    ):
        still_open: bool = False

        async def server_side() -> None:
            nonlocal still_open
            request = await server.accept()
            assert request is not None
            session = await request.accept()
            async with session:
                # Wait 3 seconds — with keep-alive, session should survive
                await asyncio.sleep(3)
                still_open = session.close_reason is None
                session.close()

        setup = _webtransport_connect_js(port, hash_b64)
        async with asyncio.TaskGroup() as tg:
            tg.create_task(server_side())
            await run_js_raw(f"""
                {setup}
                const transport = new WebTransport(url, transportOptions);
                await transport.ready;
                // Idle for 4 seconds
                await new Promise(r => setTimeout(r, 4000));
                try {{ transport.close(); }} catch (e) {{}}
                return true;
            """)

    assert still_open is True


async def test_server_close_all_connections(
    start_server: ServerFactory, run_js_raw: RunJSRaw
) -> None:
    """server.close() causes browser's transport.closed to resolve."""
    async with start_server() as (server, port, hash_b64):

        async def server_side() -> None:
            request = await server.accept()
            assert request is not None
            await request.accept()
            await asyncio.sleep(0.1)
            server.close()

        setup = _webtransport_connect_js(port, hash_b64)
        async with asyncio.TaskGroup() as tg:
            tg.create_task(server_side())
            result: Any = await run_js_raw(f"""
                {setup}
                const transport = new WebTransport(url, transportOptions);
                await transport.ready;
                try {{
                    await transport.closed;
                    return {{ closed: true }};
                }} catch (e) {{
                    return {{ closed: true, error: e.toString() }};
                }}
            """)

    assert isinstance(result, dict)
    assert result["closed"] is True
