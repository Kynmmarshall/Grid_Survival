# Online Play Architecture Draft

## Goal

Replace the current "public IP plus port forwarding" flow with a proper online-play stack that separates:

1. `transport`
2. `session`
3. `match flow`

This keeps the host-authoritative gameplay model, but stops mixing packet delivery, lobby/session setup, and menu/game orchestration in the same modules.

## Proposed Layers

### 1. Transport

Module: `online_play/transport.py`

Responsibility:

- UDP packet delivery
- Reliable resend and ACK handling for critical messages
- Latest-only delivery for high-frequency streams
- Fragmentation and reassembly
- Peer liveness and disconnect detection

Public surface:

- `NetworkManager`
- `UdpHostTransport`
- `UdpClientTransport`
- low-level transport constants and packet kinds

This layer should not know about menus, levels, player names, join codes, or ranked state.

### 2. Session

Module: `online_play/session.py`

Responsibility:

- LAN discovery
- session-facing host/client classes
- public/local IP helpers
- optional UPnP handling
- later: internet rendezvous, relay allocation, reconnect tokens, join-code resolution

Public surface:

- `NetworkHost`
- `NetworkClient`
- `LanGameFinder`
- `DiscoveredHost`
- `get_local_ip()`
- `get_public_ip()`

This is where LAN and future internet sessions should share one game-facing API.

### 3. Match Flow

Module: `online_play/match_flow.py`

Responsibility:

- message names used by the game layer
- match setup payload schemas
- parsing/building helpers for player setup and game start
- later: ready-state, reconnect, rematch, and lobby settings schemas

Public surface:

- `NetworkPlayerSetup`
- `MatchSettings`
- `MatchStartPayload`
- `build_player_setup_payload()`
- `parse_player_setup_message()`
- `build_game_start_payload()`
- `parse_game_start_message()`

This layer is the bridge between the menu/game code and the session layer.

## Near-Term Internet Design

### Session Service

Add a backend session service with these capabilities:

- create lobby
- join lobby by code
- advertise host connectivity candidates
- exchange peer candidates or assign relay endpoint
- track lobby state: waiting, ready, in_match, finished

### Preferred Connectivity Order

1. Relay-backed session for guaranteed internet play
2. Direct UDP as an optimization when rendezvous succeeds
3. LAN discovery when both peers are local

That gives us a usable default even when NAT traversal fails.

## Game Integration Plan

### Phase 1

- keep `network.py` as a compatibility facade
- move transport/session/match schema code into `online_play/`
- update menu and lobby code to use match-flow helpers

### Phase 2

- replace manual IP join in `main.py` with lobby code entry
- add backend session client
- make `NetworkHost` and `NetworkClient` session-driven instead of direct-IP driven

### Phase 3

- split tests by layer:
  - transport tests
  - session/discovery tests
  - match-flow schema tests
- remove stale TCP-era assertions

## Current Migration Status

Completed in this slice:

- extracted low-level UDP transport to `online_play/transport.py`
- extracted session/discovery helpers to `online_play/session.py`
- extracted match setup schema helpers to `online_play/match_flow.py`
- reduced `network.py` to a compatibility import facade

Still pending:

- move online setup logic out of `main.py`
- introduce backend-driven internet sessions
- update the networking test suite to match the UDP architecture
