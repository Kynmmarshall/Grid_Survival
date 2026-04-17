"""
test_network.py – Automated multiplayer networking test suite for Grid Survival.

Simulates a real host + client session entirely over localhost so no second
machine is needed.  Each test class is independent and uses a unique TCP port
allocated from a shared counter to avoid conflicts.

Run with:
    python test_network.py -v

Coverage:
    1.  Host/Client TCP connection and handshake
    2.  TCP_NODELAY is set on both sockets
    3.  Bidirectional JSON message delivery (snapshot, input_state, disconnect)
    4.  Multiple messages all delivered in order
    5.  Max-length guard rejects zero-length and oversized headers (OOM protection)
    6.  Send queue bounds – non-critical messages dropped when saturated
    7.  Critical message type list is correct
    8.  Clean disconnect detected from both sides
    9.  send_message() returns False after disconnect
   10.  Daemon-thread flag on both receive and send threads
   11.  get_public_ip() returns None or a valid IPv4 string
   12.  get_public_ip() returns None when all services are unreachable
   13.  get_local_ip() returns a valid IPv4 string
   14.  Input rate-limiting logic (mirrors game.py client branch)
"""

import socket
import threading
import time
import unittest
import urllib.request

from network import (
    MAX_MESSAGE_BYTES,
    NetworkClient,
    NetworkHost,
    NetworkManager,
    get_local_ip,
    get_public_ip,
)

# ── Port allocator ────────────────────────────────────────────────────────────
_NEXT_PORT = 55600
_PORT_LOCK = threading.Lock()


def _alloc_port() -> int:
    global _NEXT_PORT
    with _PORT_LOCK:
        p = _NEXT_PORT
        _NEXT_PORT += 1
    return p


def _wait(condition, timeout: float = 4.0, interval: float = 0.05) -> bool:
    """Poll *condition()* until it returns True or *timeout* seconds elapse."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(interval)
    return False


def _drain(manager, timeout: float = 3.0):
    """Block until at least one message arrives in *manager*'s queue."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        msgs = manager.get_messages()
        if msgs:
            return msgs
        time.sleep(0.05)
    return []


# ═════════════════════════════════════════════════════════════════════════════
# 1 · Connection handshake
# ═════════════════════════════════════════════════════════════════════════════
class TestHostClientConnection(unittest.TestCase):

    def setUp(self):
        self.port = _alloc_port()
        self.host = NetworkHost(port=self.port)
        self.client = None

    def tearDown(self):
        if self.client:
            self.client.disconnect()
        self.host.disconnect()
        time.sleep(0.1)

    def test_host_starts_listening(self):
        self.assertTrue(self.host.start_hosting())
        self.assertTrue(self.host.listening)

    def test_client_connects_and_host_accepts(self):
        self.host.start_hosting()
        self.client = NetworkClient()
        self.assertTrue(self.client.connect_to_host("127.0.0.1", self.port))
        self.assertTrue(self.client.connected)
        self.assertTrue(_wait(lambda: self.host.poll_connection()))
        self.assertTrue(self.host.connected)

    def test_tcp_nodelay_on_client_socket(self):
        self.host.start_hosting()
        self.client = NetworkClient()
        self.client.connect_to_host("127.0.0.1", self.port)
        _wait(lambda: self.host.poll_connection())
        val = self.client.socket.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY)
        self.assertEqual(val, 1, "TCP_NODELAY must be 1 on the client socket")

    def test_tcp_nodelay_on_host_accepted_socket(self):
        self.host.start_hosting()
        self.client = NetworkClient()
        self.client.connect_to_host("127.0.0.1", self.port)
        _wait(lambda: self.host.poll_connection())
        val = self.host.socket.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY)
        self.assertEqual(val, 1, "TCP_NODELAY must be 1 on the host's accepted socket")

    def test_connection_to_closed_port_fails_gracefully(self):
        self.client = NetworkClient()
        ok = self.client.connect_to_host("127.0.0.1", self.port)  # nothing listening
        self.assertFalse(ok)
        self.assertFalse(self.client.connected)
        self.assertIsNotNone(self.client.last_error)

    def test_receive_and_send_threads_are_daemons(self):
        self.host.start_hosting()
        self.client = NetworkClient()
        self.client.connect_to_host("127.0.0.1", self.port)
        _wait(lambda: self.host.poll_connection())
        self.assertTrue(self.host.receive_thread.daemon)
        self.assertTrue(self.host._send_thread.daemon)
        self.assertTrue(self.client.receive_thread.daemon)
        self.assertTrue(self.client._send_thread.daemon)



# ═════════════════════════════════════════════════════════════════════════════
# 2 · Bidirectional message delivery
# ═════════════════════════════════════════════════════════════════════════════
class TestMessageExchange(unittest.TestCase):

    def setUp(self):
        self.port = _alloc_port()
        self.host = NetworkHost(port=self.port)
        self.host.start_hosting()
        self.client = NetworkClient()
        self.client.connect_to_host("127.0.0.1", self.port)
        _wait(lambda: self.host.poll_connection())

    def tearDown(self):
        self.client.disconnect()
        self.host.disconnect()
        time.sleep(0.1)

    def test_snapshot_host_to_client(self):
        state = {"players": [{"x": 100.0, "y": 200.0, "state": "idle"}]}
        self.host.send_message("snapshot", state=state)
        msgs = _drain(self.client)
        snap = next((m for m in msgs if m.get("type") == "snapshot"), None)
        self.assertIsNotNone(snap, "Client must receive the snapshot message")
        self.assertEqual(snap["state"]["players"][0]["x"], 100.0)

    def test_input_state_client_to_host(self):
        inp = {"up": True, "down": False, "left": False, "right": True,
               "jump": False, "power_pressed": False}
        self.client.send_message("input_state", input=inp)
        msgs = _drain(self.host)
        found = next((m for m in msgs if m.get("type") == "input_state"), None)
        self.assertIsNotNone(found, "Host must receive the input_state message")
        self.assertTrue(found["input"]["up"])
        self.assertTrue(found["input"]["right"])
        self.assertFalse(found["input"]["jump"])

    def test_multiple_messages_all_delivered_in_order(self):
        for i in range(8):
            self.host.send_message("ping", seq=i)
        time.sleep(0.4)
        msgs = _drain(self.client, timeout=3.0)
        pings = [m for m in msgs if m.get("type") == "ping"]
        self.assertEqual(len(pings), 8, f"Expected 8 pings, got {len(pings)}")
        seqs = [m["seq"] for m in pings]
        self.assertEqual(seqs, list(range(8)), "Messages must arrive in send order")

    def test_disconnect_message_delivered(self):
        self.host.send_message("disconnect")
        msgs = _drain(self.client)
        self.assertTrue(any(m.get("type") == "disconnect" for m in msgs))

    def test_pause_state_delivered(self):
        self.host.send_message("pause_state", paused=True)
        msgs = _drain(self.client)
        found = next((m for m in msgs if m.get("type") == "pause_state"), None)
        self.assertIsNotNone(found)
        self.assertTrue(found["paused"])


# ═════════════════════════════════════════════════════════════════════════════
# 3 · Max-length guard (OOM / crash protection)
# ═════════════════════════════════════════════════════════════════════════════
class TestMaxLengthGuard(unittest.TestCase):

    def _raw_connect(self, port: int) -> socket.socket:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s.connect(("127.0.0.1", port))
        return s

    def _host_with_raw_client(self):
        port = _alloc_port()
        host = NetworkHost(port=port)
        host.start_hosting()
        raw = self._raw_connect(port)
        _wait(lambda: host.poll_connection())
        return host, raw

    def test_max_message_bytes_constant_is_4mb(self):
        self.assertEqual(MAX_MESSAGE_BYTES, 4 * 1024 * 1024)

    def test_zero_length_header_closes_connection(self):
        host, raw = self._host_with_raw_client()
        try:
            raw.sendall((0).to_bytes(4, "big"))
            raw.close()
            self.assertTrue(
                _wait(lambda: not host.connected),
                "Zero-length header must cause the host to drop the connection",
            )
            self.assertIsNotNone(host.last_error)
        finally:
            host.disconnect()

    def test_oversized_length_header_closes_connection(self):
        host, raw = self._host_with_raw_client()
        try:
            raw.sendall((MAX_MESSAGE_BYTES + 1).to_bytes(4, "big"))
            raw.close()
            self.assertTrue(
                _wait(lambda: not host.connected),
                "5 MB claim must cause the host to drop the connection (OOM guard)",
            )
            self.assertIsNotNone(host.last_error)
        finally:
            host.disconnect()


# ═════════════════════════════════════════════════════════════════════════════
# 4 · Send queue bounds and critical message set
# ═════════════════════════════════════════════════════════════════════════════
class TestSendQueue(unittest.TestCase):

    def setUp(self):
        self.port = _alloc_port()
        self.host = NetworkHost(port=self.port)
        self.host.start_hosting()
        self.client = NetworkClient()
        self.client.connect_to_host("127.0.0.1", self.port)
        _wait(lambda: self.host.poll_connection())

    def tearDown(self):
        self.client.disconnect()
        self.host.disconnect()
        time.sleep(0.1)

    def test_non_critical_flood_drops_without_raising(self):
        results = [self.client.send_message("input_state", input={}) for _ in range(200)]
        # Some must be dropped (False returned) but no exception is raised.
        self.assertIn(False, results, "Queue must drop non-critical messages when full")

    def test_send_returns_false_when_not_connected(self):
        self.client.disconnect()
        time.sleep(0.15)
        self.assertFalse(self.client.send_message("ping"))

    def test_critical_message_type_list(self):
        for t in ("disconnect", "snapshot", "game_start", "pause_state"):
            self.assertIn(t, NetworkManager._CRITICAL_MESSAGES,
                          f"'{t}' must be in _CRITICAL_MESSAGES")

    def test_input_state_not_critical(self):
        self.assertNotIn("input_state", NetworkManager._CRITICAL_MESSAGES)


# ═════════════════════════════════════════════════════════════════════════════
# 5 · Disconnect detection from both sides
# ═════════════════════════════════════════════════════════════════════════════
class TestDisconnect(unittest.TestCase):

    def _connected_pair(self):
        port = _alloc_port()
        host = NetworkHost(port=port)
        host.start_hosting()
        client = NetworkClient()
        client.connect_to_host("127.0.0.1", port)
        _wait(lambda: host.poll_connection())
        return host, client

    def test_client_disconnect_detected_by_host(self):
        host, client = self._connected_pair()
        client.disconnect()
        self.assertTrue(_wait(lambda: not host.connected),
                        "Host must detect client disconnect within 4 s")
        host.disconnect()

    def test_host_disconnect_detected_by_client(self):
        host, client = self._connected_pair()
        host.disconnect()
        self.assertTrue(_wait(lambda: not client.connected),
                        "Client must detect host disconnect within 4 s")
        client.disconnect()

    def test_disconnect_is_idempotent(self):
        host, client = self._connected_pair()
        # Calling disconnect() twice must not raise.
        client.disconnect()
        client.disconnect()
        host.disconnect()
        host.disconnect()


# ═════════════════════════════════════════════════════════════════════════════
# 6 · get_public_ip() and get_local_ip()
# ═════════════════════════════════════════════════════════════════════════════
class TestIpHelpers(unittest.TestCase):

    def _is_valid_ipv4(self, ip: str) -> bool:
        parts = ip.split(".")
        if len(parts) != 4:
            return False
        return all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)

    def test_get_local_ip_returns_valid_ipv4(self):
        ip = get_local_ip()
        self.assertTrue(self._is_valid_ipv4(ip), f"get_local_ip() returned invalid value: {ip!r}")

    def test_get_public_ip_returns_none_or_valid_ipv4(self):
        # Short timeout keeps the test fast when the machine is offline.
        result = get_public_ip(timeout=5.0)
        if result is None:
            return  # acceptable when offline
        self.assertTrue(self._is_valid_ipv4(result),
                        f"get_public_ip() returned non-IPv4 value: {result!r}")

    def test_get_public_ip_returns_none_when_all_services_fail(self):
        # Monkey-patch urllib.request.urlopen to always raise so we never hit
        # the real internet from this assertion.
        original = urllib.request.urlopen

        def _always_fail(url, timeout=None):
            raise OSError("test: simulated network failure")

        urllib.request.urlopen = _always_fail
        try:
            result = get_public_ip(timeout=1.0)
            self.assertIsNone(result,
                              "get_public_ip() must return None when all services are unreachable")
        finally:
            urllib.request.urlopen = original


# ═════════════════════════════════════════════════════════════════════════════
# 7 · Input rate-limiting logic (pure Python – no pygame)
# ═════════════════════════════════════════════════════════════════════════════
class TestInputRateLimiting(unittest.TestCase):
    """Mirror the decision logic from game.py's client branch."""

    _INTERVAL = 1 / 30  # matches game.py _input_send_interval

    def _should_send(self, local_input, last_sent, timer) -> bool:
        return local_input != last_sent or timer >= self._INTERVAL

    def test_sends_when_input_changes(self):
        a = {"up": False, "right": True}
        b = {"up": True, "right": True}
        self.assertTrue(self._should_send(b, a, 0.0))

    def test_no_send_when_identical_and_timer_not_elapsed(self):
        inp = {"up": False, "right": True}
        self.assertFalse(self._should_send(inp, inp, 0.001))

    def test_sends_when_timer_elapsed_even_if_input_identical(self):
        inp = {"up": False, "right": True}
        self.assertTrue(self._should_send(inp, inp, self._INTERVAL + 0.001))

    def test_sends_on_first_call_when_last_sent_is_none(self):
        inp = {"up": True, "jump": False}
        # None != dict  →  always a change on the very first send
        self.assertTrue(self._should_send(inp, None, 0.0))

    def test_no_send_when_all_false_and_timer_not_elapsed(self):
        idle = {"up": False, "down": False, "left": False,
                "right": False, "jump": False, "power_pressed": False}
        self.assertFalse(self._should_send(idle, idle, 0.005))


# ═════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    unittest.main(verbosity=2)
