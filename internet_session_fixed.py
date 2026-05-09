    def connect_to_match(self, *, endpoint: str, token: str, player_name: str) -> bool:
        parsed = self._parse_endpoint(endpoint)
        if parsed is None:
            self.last_error = f"Invalid match endpoint: {endpoint}"
            return False

        host, port = parsed
        host = self._normalize_match_host(host)
        
        # Store for later use
        self.match_endpoint = str(endpoint)
        self.match_token = str(token)
        self.player_name = str(player_name)
        self._last_host = host
        self._last_port = int(port)
        self._last_auth_ok = False
        
        try:
            self._logger.debug(
                "connect_to_match -> endpoint=%s parsed=%s token_set=%s player=%s",
                endpoint,
                f"{host}:{port}",
                bool(token),
                player_name,
            )
        except Exception:
            pass

        # === PHASE 1: Try TCP handshake (most reliable through firewalls) ===
        print(f"[DEBUG] [PHASE 1] Attempting TCP handshake to {host}:{port}...")
        tcp_auth_ok = False
        try:
            if hasattr(self, 'transport') and hasattr(self.transport, '_tcp_handshake'):
                if self.transport._tcp_handshake(host, port, token, player_name):
                    print(f"[DEBUG] [PHASE 1] TCP auth succeeded!")
                    self.session_id = self.transport.session_id
                    self._last_auth_ok = True
                    tcp_auth_ok = True
        except Exception as e:
            try:
                print(f"[DEBUG] [PHASE 1] TCP auth exception: {e}")
            except Exception:
                pass

        # If TCP auth succeeded, do UDP hello with shorter timeout (endpoint verified)
        if tcp_auth_ok:
            print(f"[DEBUG] [PHASE 1] TCP ok, now trying UDP hello with shorter timeout...")
            # Call connect_to_host which creates/manages the socket properly
            # Note: This will create ONE clean socket with ONE set of threads
            if self.connect_to_host(host, port):
                print(f"[DEBUG] [PHASE 1] SUCCESS: Connected via TCP auth + UDP hello!")
                return True
            else:
                print(f"[DEBUG] [PHASE 1] UDP hello failed after TCP auth: {self.last_error}")
        
        # === PHASE 2: Try clean UDP hello from scratch ===
        print(f"[DEBUG] [PHASE 2] Trying fresh UDP hello...")
        connected = False
        for attempt in range(1, 4):
            print(f"[DEBUG] [PHASE 2] UDP hello attempt {attempt}/3...")
            if self.connect_to_host(host, port):
                connected = True
                print(f"[DEBUG] [PHASE 2] UDP hello succeeded!")
                break
            print(f"[DEBUG] [PHASE 2] Attempt {attempt} failed: {self.last_error}")
            if attempt < 3:
                time.sleep(0.35)

        if not connected:
            # Check if connection was refused (LAN fallback case)
            if self.last_error is not None:
                lower = str(self.last_error).lower()
                if any(x in lower for x in ["econnrefused", "connection refused", "winerror 10061", "refused"]):
                    self._logger.warning("Internet connection refused; triggering LAN fallback")
                    raise InternetFallbackLAN("Internet connect refused; fallback to LAN")
            
            self.last_error = "Failed to connect via TCP or UDP"
            return False

        # === PHASE 3: Send internet_auth and wait for confirmation ===
        print(f"[DEBUG] [PHASE 3] Sending internet_auth...")
        if not self.send_message(
            "internet_auth",
            token=token,
            player=player_name,
            resume=False,
        ):
            self.last_error = "Failed to send internet_auth"
            self.disconnect()
            return False

        started = time.time()
        while time.time() - started < 5.0:
            for message in self.get_messages():
                if message.get("type") == "internet_auth_ok":
                    self.session_id = str(message.get("session_id", "")) or None
                    self._last_auth_ok = True
                    print(f"[DEBUG] [PHASE 3] SUCCESS: internet_auth_ok received!")
                    return True
                if message.get("type") == "internet_auth_error":
                    self.last_error = str(message.get("error", "auth rejected"))
                    self.disconnect()
                    print(f"[DEBUG] [PHASE 3] FAILED: {self.last_error}")
                    return False
            time.sleep(0.02)

        self.last_error = "Timed out waiting for internet_auth_ok"
        self.disconnect()
        print(f"[DEBUG] [PHASE 3] FAILED: Timeout")
        return False
