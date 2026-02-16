"""Type stubs for the web-transport native module."""

from collections.abc import AsyncIterator
from typing import Literal
from types import TracebackType

# ---------------------------------------------------------------------------
# Free functions
# ---------------------------------------------------------------------------

def generate_self_signed(
    subject_alt_names: list[str],
) -> tuple[bytes, bytes]:
    """Generate a self-signed certificate and private key.

    Uses ECDSA P-256 and a 14-day validity period (the maximum allowed by
    WebTransport for certificate pinning).

    Args:
        subject_alt_names: SANs for the certificate
            (e.g. ``["localhost", "127.0.0.1", "::1"]``).

    Returns:
        A ``(certificate_der, private_key_der)`` tuple of raw DER bytes.
    """
    ...

def certificate_hash(certificate_der: bytes) -> bytes:
    """Compute the SHA-256 fingerprint of a DER-encoded certificate.

    Args:
        certificate_der: Raw DER-encoded certificate bytes.

    Returns:
        32 bytes (SHA-256 digest).
    """
    ...

# ---------------------------------------------------------------------------
# Exceptions
#
# WebTransportError                     Base for all web-transport errors
# ├── SessionError                      Session-level failures
# │   ├── ConnectError                  Failed to establish a session
# │   │   └── SessionRejected           Server rejected with HTTP status (.status_code)
# │   ├── SessionClosed                 Session closed (either side)
# │   │   ├── SessionClosedByPeer       Peer closed (.source, .code?, .reason?)
# │   │   └── SessionClosedLocally      Local side already closed the session
# │   ├── SessionTimeout                Idle timeout expired
# │   └── ProtocolError                 QUIC / HTTP/3 protocol violation
# ├── StreamError                       Stream-level failures
# │   ├── StreamClosed                  Stream closed (either side)
# │   │   ├── StreamClosedByPeer        Peer stopped/reset (.kind, .error_code)
# │   │   └── StreamClosedLocally       Stream already finished/reset locally
# │   ├── StreamTooLongError            read(-1) data exceeded size limit
# │   └── StreamIncompleteReadError     EOF before expected bytes (.expected, .partial)
# └── DatagramError                     Datagram-level failures
#     ├── DatagramTooLargeError         Payload exceeds max datagram size
#     └── DatagramNotSupportedError     Datagrams unavailable (.reason)
# ---------------------------------------------------------------------------

class WebTransportError(Exception):
    """Base exception for all web-transport errors."""

    ...

# -- Session errors ---------------------------------------------------------

class SessionError(WebTransportError):
    """Base class for session-level errors."""

    ...

class ConnectError(SessionError):
    """Failed to establish a WebTransport session."""

    ...

class SessionRejected(ConnectError):
    """The server rejected the session request with an HTTP error status.

    Attributes:
        status_code: The HTTP status code returned by the server
            (e.g. ``403``, ``404``, ``429``).
    """

    status_code: int

class SessionClosed(SessionError):
    """The session was closed (by either side).

    Catch this to handle both :class:`SessionClosedByPeer` and
    :class:`SessionClosedLocally` uniformly.
    """

    ...

class SessionClosedByPeer(SessionClosed):
    """The peer closed the session.

    Attributes:
        source: How the session was closed:
            - ``"application"`` — the peer's application closed the session;
              *code* and *reason* are meaningful.
            - ``"transport"`` — the peer's QUIC stack closed the connection
              (e.g. protocol violation detected by the peer).
            - ``"reset"`` — the peer sent a stateless reset, typically
              because it lost all connection state (e.g. after a restart).
        code: Application error code (when ``source == "application"``),
            or ``None`` for transport-level closes and stateless resets.
        reason: Human-readable close reason, or ``""`` if not provided.
    """

    source: Literal["application", "transport", "reset"]
    code: int | None
    reason: str

class SessionClosedLocally(SessionClosed):
    """The local application already closed this session.

    Raised when an operation is attempted on a session that was closed by a
    prior call to :meth:`Session.close`.
    """

    ...

class SessionTimeout(SessionError):
    """The session timed out due to inactivity."""

    ...

class ProtocolError(SessionError):
    """A QUIC or HTTP/3 protocol violation occurred.

    Also raised when the peer sends a stream STOP_SENDING or RESET_STREAM
    with an HTTP/3 error code that cannot be mapped to a valid WebTransport
    error code.
    """

    ...

# -- Stream errors ----------------------------------------------------------

class StreamError(WebTransportError):
    """Base class for stream-level errors."""

    ...

class StreamClosed(StreamError):
    """The stream was closed (by either side).

    Catch this to handle both :class:`StreamClosedByPeer` and
    :class:`StreamClosedLocally` uniformly.
    """

    ...

class StreamClosedByPeer(StreamClosed):
    """The peer closed this stream via STOP_SENDING or RESET_STREAM.

    Attributes:
        kind: How the stream was closed:
            - ``"reset"`` — the peer sent RESET_STREAM (receive side),
              abandoning transmission of data on the stream.
            - ``"stop"`` — the peer sent STOP_SENDING (send side),
              requesting that we stop writing to the stream.
        error_code: The application error code from the peer.
    """

    kind: Literal["reset", "stop"]
    error_code: int

class StreamClosedLocally(StreamClosed):
    """The stream was already finished or reset locally."""

    ...

class StreamTooLongError(StreamError):
    """A ``read()`` call exceeded the maximum allowed data size.

    Raised when reading until EOF (``read(-1)``) and the incoming data
    exceeds the internal size limit before the stream finishes.
    """

    ...

class StreamIncompleteReadError(StreamError):
    """EOF was reached before enough bytes were read.

    Raised by :meth:`RecvStream.readexactly` when the stream finishes
    before *n* bytes have been received.  Modeled after
    :class:`asyncio.IncompleteReadError`.

    Attributes:
        expected: Number of bytes that were requested.
        partial: The bytes that were successfully read before EOF.
    """

    expected: int
    partial: bytes

# -- Datagram errors --------------------------------------------------------

class DatagramError(WebTransportError):
    """Base class for datagram-level errors."""

    ...

class DatagramTooLargeError(DatagramError):
    """The datagram payload exceeds the maximum size for this session."""

    ...

class DatagramNotSupportedError(DatagramError):
    """Datagrams are not supported by the peer or are disabled locally.

    Attributes:
        reason: Why datagrams are unavailable:
            - ``"unsupported_by_peer"`` — the peer does not support
              receiving datagram frames.
            - ``"disabled_locally"`` — datagram support is disabled locally.
    """

    reason: Literal["unsupported_by_peer", "disabled_locally"]

    ...

# ---------------------------------------------------------------------------
# Core classes
# ---------------------------------------------------------------------------

class Server:
    """WebTransport server.

    Listens for incoming sessions over QUIC. Use as an async context manager
    and iterate with ``async for`` to accept requests::

        async with Server(certificate_chain=[cert], private_key=key) as srv:
            async for request in srv:
                session = await request.accept()

    Args:
        certificate_chain: DER-encoded certificates (leaf first).
        private_key: DER-encoded PKCS#8 private key.
        bind: Address to listen on (default ``"[::]:4433"``).
        congestion_control: Algorithm to use — ``"default"``, ``"throughput"``,
            or ``"low_latency"`` (default ``"default"``).
        max_idle_timeout: Maximum idle time in seconds before the connection
            is closed. ``None`` disables the timeout (default ``30``).
        keep_alive_interval: Interval in seconds between QUIC keep-alive
            pings. ``None`` disables keep-alives (default ``None``).
    """

    def __init__(
        self,
        *,
        certificate_chain: list[bytes],
        private_key: bytes,
        bind: str = "[::]:4433",
        congestion_control: Literal["default", "throughput", "low_latency"] = "default",
        max_idle_timeout: float | None = 30,
        keep_alive_interval: float | None = None,
    ) -> None: ...
    async def __aenter__(self) -> Server: ...
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None: ...
    def __aiter__(self) -> AsyncIterator[SessionRequest]: ...
    async def __anext__(self) -> SessionRequest: ...
    async def accept(self) -> SessionRequest | None:
        """Wait for the next incoming session request.

        Returns ``None`` when the server has been closed.
        """
        ...

    def close(self, code: int = 0, reason: str = "") -> None:
        """Close all connections immediately and stop accepting new ones.

        Args:
            code: Application error code (default ``0``).
            reason: Human-readable close reason (default ``""``).
        """
        ...

    async def wait_closed(self) -> None:
        """Wait for all connections to be cleanly shut down."""
        ...

    @property
    def local_addr(self) -> tuple[str, int]:
        """The local ``(host, port)`` the server is bound to."""
        ...

class SessionRequest:
    """An incoming WebTransport session request.

    Obtained from :meth:`Server.accept` or by iterating a :class:`Server`.
    Inspect the request and call :meth:`accept` or :meth:`reject`.
    """

    @property
    def url(self) -> str:
        """The URL requested by the client."""
        ...

    async def accept(self) -> Session:
        """Accept the session request.

        Returns:
            An established :class:`Session`.
        """
        ...

    async def reject(self, status_code: int = 404) -> None:
        """Reject the session request with an HTTP status code.

        Args:
            status_code: HTTP status code (e.g. ``403``, ``404``, ``429``).
        """
        ...

class Client:
    """WebTransport client.

    Use as an async context manager::

        async with Client() as client:
            session = await client.connect("https://example.com:4433")

    Certificate verification defaults to the system root CA store. Use
    ``server_certificate_hashes`` to pin specific certificates, or
    ``no_cert_verification=True`` to disable verification entirely (testing
    only).

    Args:
        server_certificate_hashes: Pin against these SHA-256 certificate
            hashes instead of using system roots.
        no_cert_verification: Disable all certificate verification.
            **Dangerous** — only for local development.
        congestion_control: Algorithm to use — ``"default"``, ``"throughput"``,
            or ``"low_latency"`` (default ``"default"``).
        max_idle_timeout: Maximum idle time in seconds before the connection
            is closed. ``None`` disables the timeout (default ``30``).
        keep_alive_interval: Interval in seconds between QUIC keep-alive
            pings. ``None`` disables keep-alives (default ``None``).
    """

    def __init__(
        self,
        *,
        server_certificate_hashes: list[bytes] | None = None,
        no_cert_verification: bool = False,
        congestion_control: Literal["default", "throughput", "low_latency"] = "default",
        max_idle_timeout: float | None = 30,
        keep_alive_interval: float | None = None,
    ) -> None: ...
    async def __aenter__(self) -> Client: ...
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None: ...
    async def connect(self, url: str) -> Session:
        """Open a WebTransport session to the given URL.

        Args:
            url: An ``https://`` URL to connect to.

        Returns:
            An established :class:`Session`.

        Raises:
            ConnectError: If the connection cannot be established.
        """
        ...

class Session:
    """An established WebTransport session.

    Obtained from :meth:`SessionRequest.accept` (server) or
    :meth:`Client.connect` (client). Use as an async context manager to
    ensure the session is closed on exit::

        async with session:
            send, recv = await session.open_bi()
            ...
    """

    async def __aenter__(self) -> Session: ...
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None: ...

    # -- Streams ------------------------------------------------------------

    async def open_bi(self) -> tuple[SendStream, RecvStream]:
        """Open a new bidirectional stream.

        Returns:
            A ``(send, recv)`` stream pair.
        """
        ...

    async def open_uni(self) -> SendStream:
        """Open a new unidirectional (send-only) stream.

        Returns:
            A :class:`SendStream`.
        """
        ...

    async def accept_bi(self) -> tuple[SendStream, RecvStream]:
        """Wait for the peer to open a bidirectional stream.

        Returns:
            A ``(send, recv)`` stream pair.
        """
        ...

    async def accept_uni(self) -> RecvStream:
        """Wait for the peer to open a unidirectional stream.

        Returns:
            A :class:`RecvStream`.
        """
        ...

    # -- Datagrams ----------------------------------------------------------

    async def send_datagram(self, data: bytes) -> None:
        """Send an unreliable datagram.

        Args:
            data: Payload bytes. Must not exceed :attr:`max_datagram_size`.

        Raises:
            DatagramTooLargeError: If *data* exceeds the maximum size.
        """
        ...

    async def receive_datagram(self) -> bytes:
        """Wait for and return the next incoming datagram."""
        ...

    # -- Lifecycle ----------------------------------------------------------

    def close(self, code: int = 0, reason: str = "") -> None:
        """Close the session immediately.

        Args:
            code: Application error code (default ``0``).
            reason: Human-readable close reason (default ``""``).
        """
        ...

    async def wait_closed(self) -> None:
        """Wait until the session is closed (for any reason)."""
        ...

    # -- Properties ---------------------------------------------------------

    @property
    def max_datagram_size(self) -> int:
        """Maximum payload size for :meth:`send_datagram`."""
        ...

    @property
    def remote_address(self) -> tuple[str, int]:
        """The remote peer's ``(host, port)``."""
        ...

    @property
    def rtt(self) -> float:
        """Current estimated round-trip time in seconds."""
        ...

class SendStream:
    """A writable QUIC stream.

    Use as an async context manager: :meth:`finish` is called on clean exit,
    :meth:`reset` on exception::

        async with send:
            await send.write(b"hello")
    """

    async def __aenter__(self) -> SendStream: ...
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None: ...
    async def write(self, data: bytes) -> None:
        """Write all data to the stream.

        Args:
            data: Bytes to write. Guaranteed to be fully written or raise.
        """
        ...

    async def write_some(self, data: bytes) -> int:
        """Write some data, returning the number of bytes written.

        Low-level API. May write fewer bytes than ``len(data)`` due to flow
        control. Prefer :meth:`write` unless you need fine-grained control.

        Args:
            data: Bytes to write.

        Returns:
            Number of bytes actually written.
        """
        ...

    def finish(self) -> None:
        """Gracefully close the stream, signaling EOF to the peer."""
        ...

    def reset(self, error_code: int = 0) -> None:
        """Abruptly reset the stream.

        Args:
            error_code: Application error code (default ``0``).
        """
        ...

    @property
    def priority(self) -> int:
        """Stream scheduling priority (higher = higher priority)."""
        ...

    @priority.setter
    def priority(self, value: int) -> None: ...

class RecvStream:
    """A readable QUIC stream.

    Supports ``async for`` to iterate over incoming chunks until EOF::

        async for chunk in recv:
            process(chunk)
    """

    async def __aenter__(self) -> RecvStream: ...
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None: ...
    def __aiter__(self) -> AsyncIterator[bytes]: ...
    async def __anext__(self) -> bytes: ...
    async def read(self, n: int = -1) -> bytes:
        """Read up to *n* bytes from the stream, or until EOF if *n* is ``-1``.

        Returns an empty ``bytes`` at EOF.

        Args:
            n: Maximum number of bytes to read. Pass ``-1`` (the default)
                to read until EOF.
        """
        ...

    async def readexactly(self, n: int) -> bytes:
        """Read exactly *n* bytes.

        Args:
            n: Number of bytes to read.

        Raises:
            StreamIncompleteReadError: If EOF is reached before *n* bytes.
        """
        ...

    def stop(self, error_code: int = 0) -> None:
        """Tell the peer to stop sending on this stream.

        Args:
            error_code: Application error code (default ``0``).
        """
        ...
