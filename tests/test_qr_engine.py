"""Unit tests for QR payload builders — no DB, no network needed."""
import pytest
from app.services.qr_engine import (
    UPIParams, validate_vpa, parse_amount,
    build_upi, build_url, build_wifi,
    build_vcard, build_email, build_sms, build_geo,
)


class TestVPA:
    def test_valid(self):
        assert validate_vpa("name@upi")
        assert validate_vpa("9876543210@paytm")
        assert validate_vpa("merchant@okaxis")
        assert validate_vpa("user.name@ybl")

    def test_invalid(self):
        assert not validate_vpa("")
        assert not validate_vpa("noatsign")
        assert not validate_vpa("@noleft")
        assert not validate_vpa("user@1")   # numeric-only provider


class TestParseAmount:
    def test_valid(self):
        assert parse_amount("100") == 100.0
        assert parse_amount("₹1,000.50") == 1000.5
        assert parse_amount("0.01") == 0.01

    def test_invalid(self):
        assert parse_amount("abc") is None
        assert parse_amount("0") is None
        assert parse_amount("-50") is None


class TestUPI:
    def test_basic(self):
        r = build_upi(UPIParams("a@b", "Name"))
        assert r.startswith("upi://pay?")
        assert "cu=INR" in r
        assert "pa=" in r and "pn=" in r

    def test_with_amount(self):
        r = build_upi(UPIParams("a@b", "Name", amount=250.0))
        assert "am=250.00" in r

    def test_skip_zero_amount(self):
        r = build_upi(UPIParams("a@b", "Name", amount=0))
        assert "am=" not in r

    def test_special_chars_encoded(self):
        r = build_upi(UPIParams("a@b", "Café & Co"))
        assert "Café" not in r     # must be percent-encoded


class TestWifi:
    def test_wpa(self):
        r = build_wifi("MyNet", "pass123", "WPA")
        assert "T:WPA" in r and "S:MyNet" in r and "P:pass123" in r

    def test_open(self):
        r = build_wifi("OpenNet", "", "nopass")
        assert "T:nopass" in r

    def test_hidden(self):
        r = build_wifi("Hidden", "pw", hidden=True)
        assert "H:true" in r


class TestVCard:
    def test_full(self):
        r = build_vcard("John", "+91999", "j@example.com", "ACME")
        assert "BEGIN:VCARD" in r
        assert "FN:John" in r
        assert "TEL:+91999" in r
        assert "ORG:ACME" in r


class TestOthers:
    def test_url_prefix(self):
        assert build_url("example.com").startswith("https://")
        assert build_url("https://x.com") == "https://x.com"

    def test_email(self):
        r = build_email("a@b.com", subject="Hi")
        assert "mailto:a@b.com" in r and "subject=Hi" in r

    def test_sms(self):
        r = build_sms("+911234", "Hello")
        assert r.startswith("sms:+911234")
        assert "body=" in r

    def test_geo(self):
        r = build_geo(28.6139, 77.209)
        assert r.startswith("geo:28.6139,77.209")
