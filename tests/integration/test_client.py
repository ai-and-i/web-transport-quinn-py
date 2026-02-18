"""Integration tests for client connection errors and configuration."""

import asyncio

import pytest

import web_transport


@pytest.mark.asyncio
async def test_connect_invalid_url(cert_hash):
    """connect("not-a-url") -> ValueError."""
    async with web_transport.Client(server_certificate_hashes=[cert_hash]) as client:
        with pytest.raises(ValueError):
            await client.connect("not-a-url")


@pytest.mark.asyncio
async def test_connect_wrong_cert_hash(self_signed_cert):
    """Wrong server_certificate_hashes -> ConnectError or ProtocolError."""
    cert, key = self_signed_cert

    async with web_transport.Server(
        certificate_chain=[cert], private_key=key, bind="[::1]:0"
    ) as server:
        _, port = server.local_addr

        async def server_task():
            # Server must be accepting for the TLS handshake to occur
            await server.accept()

        async def client_task():
            wrong_hash = b"\x00" * 32
            async with web_transport.Client(
                server_certificate_hashes=[wrong_hash]
            ) as client:
                with pytest.raises(
                    (web_transport.ConnectError, web_transport.ProtocolError)
                ):
                    await client.connect(f"https://[::1]:{port}")

        server_t = asyncio.create_task(server_task())
        client_t = asyncio.create_task(client_task())

        # Wait for client to finish (it should fail fast)
        await asyncio.wait_for(client_t, timeout=10.0)

        # Cancel server accept since the handshake failed
        server_t.cancel()
        try:
            await server_t
        except (asyncio.CancelledError, Exception):
            pass


@pytest.mark.asyncio
async def test_connect_no_server():
    """Connect to port with no listener -> ConnectError or timeout."""
    async with web_transport.Client(
        server_certificate_hashes=[b"\x00" * 32],
        max_idle_timeout=1.0,
    ) as client:
        with pytest.raises((web_transport.ConnectError, web_transport.SessionTimeout)):
            await asyncio.wait_for(
                client.connect("https://[::1]:19999"),
                timeout=5.0,
            )


@pytest.mark.asyncio
async def test_connect_after_close(self_signed_cert, cert_hash):
    """client.close() then connect() -> error."""
    cert, key = self_signed_cert

    async with web_transport.Server(
        certificate_chain=[cert], private_key=key, bind="[::1]:0"
    ) as server:
        _, port = server.local_addr

        async with web_transport.Client(
            server_certificate_hashes=[cert_hash]
        ) as client:
            client.close()
            with pytest.raises(Exception):
                await client.connect(f"https://[::1]:{port}")


@pytest.mark.asyncio
async def test_no_cert_verification_mode(self_signed_cert):
    """no_cert_verification=True connects without pinning."""
    cert, key = self_signed_cert

    async with web_transport.Server(
        certificate_chain=[cert], private_key=key, bind="[::1]:0"
    ) as server:
        _, port = server.local_addr

        async def server_task():
            request = await server.accept()
            assert request is not None
            session = await request.accept()
            session.close()

        async def client_task():
            async with web_transport.Client(no_cert_verification=True) as client:
                session = await client.connect(f"https://[::1]:{port}")
                assert session is not None
                session.close()

        await asyncio.gather(
            asyncio.create_task(server_task()),
            asyncio.create_task(client_task()),
        )


@pytest.mark.asyncio
async def test_congestion_throughput(self_signed_cert, cert_hash):
    """congestion_control="throughput" -> connection works."""
    cert, key = self_signed_cert

    async with web_transport.Server(
        certificate_chain=[cert],
        private_key=key,
        bind="[::1]:0",
        congestion_control="throughput",
    ) as server:
        _, port = server.local_addr

        async def server_task():
            request = await server.accept()
            assert request is not None
            session = await request.accept()
            session.close()

        async def client_task():
            async with web_transport.Client(
                server_certificate_hashes=[cert_hash],
                congestion_control="throughput",
            ) as client:
                session = await client.connect(f"https://[::1]:{port}")
                assert session is not None
                session.close()

        await asyncio.gather(
            asyncio.create_task(server_task()),
            asyncio.create_task(client_task()),
        )


@pytest.mark.asyncio
async def test_congestion_low_latency(self_signed_cert, cert_hash):
    """congestion_control="low_latency" -> connection works."""
    cert, key = self_signed_cert

    async with web_transport.Server(
        certificate_chain=[cert],
        private_key=key,
        bind="[::1]:0",
        congestion_control="low_latency",
    ) as server:
        _, port = server.local_addr

        async def server_task():
            request = await server.accept()
            assert request is not None
            session = await request.accept()
            session.close()

        async def client_task():
            async with web_transport.Client(
                server_certificate_hashes=[cert_hash],
                congestion_control="low_latency",
            ) as client:
                session = await client.connect(f"https://[::1]:{port}")
                assert session is not None
                session.close()

        await asyncio.gather(
            asyncio.create_task(server_task()),
            asyncio.create_task(client_task()),
        )


@pytest.mark.asyncio
async def test_idle_timeout_fires(self_signed_cert, cert_hash):
    """max_idle_timeout=0.5 -> SessionTimeout after inactivity."""
    cert, key = self_signed_cert

    async with web_transport.Server(
        certificate_chain=[cert],
        private_key=key,
        bind="[::1]:0",
        max_idle_timeout=0.5,
    ) as server:
        _, port = server.local_addr

        async def server_task():
            request = await server.accept()
            assert request is not None
            session = await request.accept()
            await asyncio.wait_for(session.wait_closed(), timeout=5.0)
            reason = session.close_reason
            assert isinstance(
                reason, (web_transport.SessionTimeout, web_transport.SessionClosed)
            )

        async def client_task():
            async with web_transport.Client(
                server_certificate_hashes=[cert_hash],
                max_idle_timeout=0.5,
            ) as client:
                session = await client.connect(f"https://[::1]:{port}")
                # Do nothing — let the idle timeout fire
                await asyncio.wait_for(session.wait_closed(), timeout=5.0)
                reason = session.close_reason
                assert isinstance(
                    reason,
                    (web_transport.SessionTimeout, web_transport.SessionClosed),
                )

        await asyncio.gather(
            asyncio.create_task(server_task()),
            asyncio.create_task(client_task()),
        )


@pytest.mark.asyncio
async def test_keep_alive_prevents_timeout(self_signed_cert, cert_hash):
    """keep_alive prevents idle timeout."""
    cert, key = self_signed_cert

    async with web_transport.Server(
        certificate_chain=[cert],
        private_key=key,
        bind="[::1]:0",
        max_idle_timeout=0.5,
        keep_alive_interval=0.1,
    ) as server:
        _, port = server.local_addr

        async def server_task():
            request = await server.accept()
            assert request is not None
            session = await request.accept()
            # Wait longer than the idle timeout
            await asyncio.sleep(1.0)
            # Session should still be alive
            assert session.close_reason is None
            session.close()

        async def client_task():
            async with web_transport.Client(
                server_certificate_hashes=[cert_hash],
                max_idle_timeout=0.5,
                keep_alive_interval=0.1,
            ) as client:
                session = await client.connect(f"https://[::1]:{port}")
                await asyncio.sleep(1.0)
                # Session should still be alive
                assert session.close_reason is None
                session.close()

        await asyncio.gather(
            asyncio.create_task(server_task()),
            asyncio.create_task(client_task()),
        )


@pytest.mark.asyncio
async def test_client_wait_closed():
    """client.wait_closed() returns after close()."""
    client = web_transport.Client(server_certificate_hashes=[b"\x00" * 32])
    await client.__aenter__()
    client.close()
    await asyncio.wait_for(client.wait_closed(), timeout=5.0)
    await client.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_idle_timeout_disabled(self_signed_cert, cert_hash):
    """max_idle_timeout=None -> alive after 2s."""
    cert, key = self_signed_cert

    async with web_transport.Server(
        certificate_chain=[cert],
        private_key=key,
        bind="[::1]:0",
        max_idle_timeout=None,
    ) as server:
        _, port = server.local_addr

        async def server_task():
            request = await server.accept()
            assert request is not None
            session = await request.accept()
            await asyncio.sleep(2.0)
            assert session.close_reason is None
            session.close()

        async def client_task():
            async with web_transport.Client(
                server_certificate_hashes=[cert_hash],
                max_idle_timeout=None,
            ) as client:
                session = await client.connect(f"https://[::1]:{port}")
                await asyncio.sleep(2.0)
                assert session.close_reason is None
                session.close()

        await asyncio.gather(
            asyncio.create_task(server_task()),
            asyncio.create_task(client_task()),
        )
