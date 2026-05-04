"""Layered tests for the extracted online-play modules."""

from __future__ import annotations

import json
import socket
import threading
import time
import unittest
import urllib.request
from unittest import mock

from online_play.match_flow import (
    CRITICAL_MESSAGE_TYPES,
    LATEST_ONLY_MESSAGE_TYPES,
    MSG_GAME_START,
    MSG_INPUT_STATE,
    MSG_PAUSE_STATE,
    MSG_PLAYER_SETUP,
    MatchSettings,
    MatchStartPayload,
    NetworkPlayerSetup,
    build_game_start_payload,
    build_player_setup_payload,
    parse_game_start_message,
    parse_player_setup_message,
)
from online_play.session import (
    DISCOVERY_MAGIC,
    DISCOVERY_PORT,
    LanGameFinder,
    NetworkClient,
    NetworkHost,
    get_local_ip,
    get_public_ip,
)
from online_play.transport import (
    GAME_UDP_PORT_OFFSET,
    HELLO_TIMEOUT,
    InputState,
    MAX_MESSAGE_BYTES,
    PlayerState,
    UdpClientTransport,
    UdpHostTransport,
)


_NEXT_PORT = 55600
_PORT_LOCK = threading.Lock()


def _alloc_port() -> int:
    global _NEXT_PORT
    with _PORT_LOCK:
        port = _NEXT_PORT
        _NEXT_PORT += 1
    return port


def _wait(condition, timeout: float = 4.0, interval: float = 0.05) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(interval)
    return False


def _drain(manager, timeout: float = 3.0) -> list[dict]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        messages = manager.get_messages()
        if messages:
            return messages
        time.sleep(0.05)
    return []


class TransportPairTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.port = _alloc_port()
        self.host = UdpHostTransport(port=self.port)
        self.client = UdpClientTransport()
        self.assertTrue(self.host.start_hosting())
        self.assertTrue(self.client.connect_to_host("127.0.0.1", self.port))
        self.assertTrue(_wait(lambda: self.host.poll_connection()))

    def tearDown(self) -> None:
        self.client.disconnect()
        self.host.disconnect()
        time.sleep(0.05)


class TestTransportLayer(TransportPairTestCase):
    def test_transport_connection_and_threads(self) -> None:
        self.assertTrue(self.host.connected)
        self.assertTrue(self.client.connected)
        self.assertTrue(self.host.receive_thread.daemon)
        self.assertTrue(self.host._send_thread.daemon)
        self.assertTrue(self.client.receive_thread.daemon)
        self.assertTrue(self.client._send_thread.daemon)

    def test_bidirectional_message_delivery(self) -> None:
        self.host.send_message("snapshot", state={"players": [{"x": 10.0}]})
        snapshot_messages = _drain(self.client)
        snapshot = next((m for m in snapshot_messages if m.get("type") == "snapshot"), None)
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot["state"]["players"][0]["x"], 10.0)

        self.client.send_message("input_state", input={"left": True, "jump": False})
        input_messages = _drain(self.host)
        payload = next((m for m in input_messages if m.get("type") == "input_state"), None)
        self.assertIsNotNone(payload)
        self.assertTrue(payload["input"]["left"])
        self.assertFalse(payload["input"]["jump"])

    def test_reliable_messages_arrive_in_order(self) -> None:
        for seq in range(8):
            self.host.send_message("ping", seq=seq)
        time.sleep(0.4)
        messages = _drain(self.client)
        pings = [message for message in messages if message.get("type") == "ping"]
        self.assertEqual([message["seq"] for message in pings], list(range(8)))

    def test_large_payload_is_fragmented_and_reassembled(self) -> None:
        blob = "x" * 9000
        self.host.send_message("snapshot", state={"blob": blob})
        messages = _drain(self.client)
        snapshot = next((m for m in messages if m.get("type") == "snapshot"), None)
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot["state"]["blob"], blob)

    def test_latest_only_stream_keeps_newest_input(self) -> None:
        for idx in range(50):
            self.client.send_message("input_state", input={"seq": idx, "right": bool(idx % 2)})
        messages = _drain(self.host)
        payload = next((m for m in messages if m.get("type") == "input_state"), None)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["input"]["seq"], 49)

    def test_disconnect_detection_and_send_after_disconnect(self) -> None:
        self.client.disconnect()
        self.assertTrue(_wait(lambda: not self.host.connected))
        self.assertFalse(self.host.send_message("ping"))

    def test_transport_constants_and_models(self) -> None:
        self.assertEqual(MAX_MESSAGE_BYTES, 4 * 1024 * 1024)
        self.assertEqual(GAME_UDP_PORT_OFFSET, 0)
        self.assertGreater(HELLO_TIMEOUT, 0.0)
        self.assertEqual(
            InputState.from_mapping({"up": True, "power_pressed": 1}).to_dict(),
            {
                "up": True,
                "down": False,
                "left": False,
                "right": False,
                "jump": False,
                "power_pressed": True,
            },
        )
        player = PlayerState(1.0, 2.0, "left", "idle", False, False, False)
        self.assertEqual(player.facing, "left")


class TestSessionLayer(unittest.TestCase):
    def test_session_host_and_client_connect(self) -> None:
        port = _alloc_port()
        host = NetworkHost(port=port)
        client = NetworkClient()
        try:
            self.assertTrue(host.start_hosting())
            self.assertTrue(client.connect_to_host("127.0.0.1", port))
            self.assertTrue(_wait(lambda: host.poll_connection()))
        finally:
            client.disconnect()
            host.disconnect()

    def test_lan_game_finder_parses_host_announce(self) -> None:
        finder = LanGameFinder()
        self.assertTrue(finder.start())
        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            target = ("127.0.0.1", int(finder.socket.getsockname()[1]))
            payload = json.dumps(
                {
                    "magic": DISCOVERY_MAGIC,
                    "type": "host_announce",
                    "host_name": "Test Host",
                    "machine_name": "TestMachine",
                    "port": DISCOVERY_PORT,
                }
            ).encode("utf-8")
            sender.sendto(payload, target)
            hosts: list = []
            deadline = time.time() + 2.0
            while time.time() < deadline and not hosts:
                hosts = finder.poll_hosts()
                if not hosts:
                    time.sleep(0.05)
            self.assertTrue(hosts)
            self.assertEqual(hosts[0].host_name, "Test Host")
            self.assertEqual(hosts[0].machine_name, "TestMachine")
        finally:
            sender.close()
            finder.close()

    def test_get_local_ip_returns_ipv4(self) -> None:
        ip = get_local_ip()
        parts = ip.split(".")
        self.assertEqual(len(parts), 4)
        self.assertTrue(all(part.isdigit() and 0 <= int(part) <= 255 for part in parts))

    def test_get_public_ip_returns_none_when_services_fail(self) -> None:
        with mock.patch.object(urllib.request, "urlopen", side_effect=OSError("offline")):
            self.assertIsNone(get_public_ip(timeout=0.01))


class TestMatchFlowLayer(unittest.TestCase):
    def test_build_and_parse_player_setup(self) -> None:
        setup = NetworkPlayerSetup(name="A", character="Mage")
        message = build_player_setup_payload(setup)
        parsed = parse_player_setup_message(message)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.name, "A")
        self.assertEqual(parsed.character, "Mage")

    def test_build_and_parse_game_start(self) -> None:
        payload = MatchStartPayload(
            players=[
                NetworkPlayerSetup(name="A", character="Mage"),
                NetworkPlayerSetup(name="B", character="Knight"),
            ],
            local_player_index=1,
            settings=MatchSettings(level_id=2, target_score=5),
        )
        parsed = parse_game_start_message(build_game_start_payload(payload))
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.local_player_index, 1)
        self.assertEqual(parsed.settings.level_id, 2)
        self.assertEqual(parsed.settings.target_score, 5)
        self.assertEqual([player.name for player in parsed.players], ["A", "B"])

    def test_invalid_game_start_payload_returns_none(self) -> None:
        self.assertIsNone(parse_game_start_message({"players": [{"name": "solo"}]}))
        self.assertIsNone(parse_game_start_message({"players": "bad"}))

    def test_match_flow_message_sets(self) -> None:
        self.assertIn(MSG_PLAYER_SETUP, CRITICAL_MESSAGE_TYPES)
        self.assertIn(MSG_GAME_START, CRITICAL_MESSAGE_TYPES)
        self.assertIn(MSG_PAUSE_STATE, CRITICAL_MESSAGE_TYPES)
        self.assertIn(MSG_INPUT_STATE, LATEST_ONLY_MESSAGE_TYPES)


if __name__ == "__main__":
    unittest.main(verbosity=2)
