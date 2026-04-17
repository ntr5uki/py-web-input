from __future__ import annotations

from datetime import date
import unittest
from unittest.mock import patch

from network_input.auth import PairingManager


class PairingManagerTests(unittest.TestCase):
    def test_request_pair_returns_same_pending_request(self) -> None:
        pairing = PairingManager()

        first = pairing.request_pair("client-a", "192.168.1.9", "ua")
        second = pairing.request_pair("client-a", "192.168.1.9", "ua")

        self.assertEqual(first.request_id, second.request_id)
        self.assertEqual(first.status, "pending")

    def test_approved_session_is_valid_until_local_day_changes(self) -> None:
        pairing = PairingManager()
        request = pairing.request_pair("client-a", "192.168.1.9", "ua")
        approved = pairing.approve_request(request.request_id)

        self.assertTrue(pairing.validate_session("client-a", approved.session_token))

        tomorrow = date(2026, 4, 18)
        with patch.object(pairing, "_today", return_value=tomorrow):
            self.assertFalse(pairing.validate_session("client-a", approved.session_token))
            self.assertEqual(pairing.get_pair_status("client-a", approved.session_token), {"state": "unpaired"})

    def test_logout_invalidates_current_session(self) -> None:
        pairing = PairingManager()
        request = pairing.request_pair("client-a", "192.168.1.9", "ua")
        approved = pairing.approve_request(request.request_id)

        pairing.logout("client-a", approved.session_token)

        self.assertFalse(pairing.validate_session("client-a", approved.session_token))
        self.assertEqual(pairing.get_pair_status("client-a", approved.session_token), {"state": "logged_out", "request_id": request.request_id})
