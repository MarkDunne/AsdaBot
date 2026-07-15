"""Tests for asdabot's own login logic — token classification and profile mapping.

These guard the two pieces of pure logic that decide whether a login is real:
ASDA mints guest SLAS tokens on first page load (a live bug we shipped once),
and the CRM profile response must map cleanly onto the stored account.
"""

import base64
import json

import pytest

from asdabot.browser import _extract_profile, _is_logged_in


def make_jwt(isb: str) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"isb": isb}).encode()).decode().rstrip("=")
    return f"header.{payload}.signature"


def test_guest_session_is_not_a_login():
    cookies = {
        "SLAS.AUTH_TOKEN": make_jwt("uido:slas::upn:Guest::uidn:Guest User::gcid:abc::chid:ASD"),
        "SLAS.REFRESH_TOKEN": "a-refresh-token",
    }
    assert not _is_logged_in(cookies)


def test_registered_session_is_a_login():
    cookies = {
        "SLAS.AUTH_TOKEN": make_jwt("uido:azure_adb2c-signin-bjgs_prd::upn:1234::uidn:Mark"),
        "SLAS.REFRESH_TOKEN": "a-refresh-token",
    }
    assert _is_logged_in(cookies)


def test_missing_or_malformed_cookies_are_not_a_login():
    assert not _is_logged_in({})
    assert not _is_logged_in({"SLAS.AUTH_TOKEN": make_jwt("uido:azure_adb2c-signin::upn:1")})
    assert not _is_logged_in({"SLAS.AUTH_TOKEN": "not.a.jwt", "SLAS.REFRESH_TOKEN": "r"})


def test_extract_profile_maps_the_default_address():
    profile_response = {
        "profile": {
            "additionalInfo": {"cnc_store_id": "9999", "firstName": "Ada", "lastName": "Lovelace"}
        },
        "addresses": [
            {"line1": "1 Old Road", "city": "Testville", "default": False},
            {
                "line1": "123 Fictional Lane",
                "line2": "Unit 9",
                "city": "Exampleton",
                "postcode": "AA1 1AA",
                "latitude": "50.0",
                "longitude": "-5.0",
                "addressType": "House",
                "crmAddressId": "crm-1",
                "default": True,
            },
        ],
    }

    store_id, address = _extract_profile(profile_response)

    assert store_id == "9999"
    assert address["address1"] == "123 Fictional Lane"
    assert address["postcode"] == "AA11AA"  # slot APIs need the space stripped
    assert address["crm_address_id"] == "crm-1"
    assert address["first_name"] == "Ada"


def test_extract_profile_refuses_an_account_without_an_address():
    with pytest.raises(LookupError):
        _extract_profile({"profile": {}, "addresses": []})
