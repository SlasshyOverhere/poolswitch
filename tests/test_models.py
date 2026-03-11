from __future__ import annotations

from datetime import timedelta, timezone

from poolswitch.models import APIKeyState, utc_now


def test_utc_now_is_aware() -> None:
    now = utc_now()
    assert now.tzinfo is not None
    assert now.tzinfo.utcoffset(now) is not None
    assert now.tzinfo == timezone.utc


def test_is_in_cooldown() -> None:
    state = APIKeyState(key_id="demo")
    assert state.is_in_cooldown is False

    state.cooldown_until = utc_now() + timedelta(seconds=5)
    assert state.is_in_cooldown is True

    state.cooldown_until = utc_now() - timedelta(seconds=5)
    assert state.is_in_cooldown is False

