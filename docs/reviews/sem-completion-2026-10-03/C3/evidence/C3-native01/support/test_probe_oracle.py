"""Offline accounting controls reject incorrect owner, order and pool release."""

import probe_models as m
import pytest
from probe_oracle import verify_leases

IDENTITY = "nutmeg@0.1.0:" + "0" * 64


def events() -> list[m.QuotaEvent]:
    return [
        m.QuotaEvent(
            timestamp_utc=f"2026-10-03T20:00:0{index}+00:00",
            pid=10,
            id=1 if index < 2 else 2,
            event="admitted" if index % 2 == 0 else "released",
            extension=IDENTITY,
            bytes=128,
            pool_reserved=128 if index % 2 == 0 else 0,
        )
        for index in range(4)
    ]


def test_exact_actual_reservation_and_release_sequence() -> None:
    verify_leases(events(), 10, 128, IDENTITY)


def test_wrong_server_pid_or_native_identity_refuses() -> None:
    with pytest.raises(ValueError, match="actual server PID"):
        verify_leases(events(), 11, 128, IDENTITY)
    with pytest.raises(ValueError, match="actual server PID"):
        verify_leases(events(), 10, 128, IDENTITY.replace("nutmeg", "argentea"))


def test_release_request_is_not_completed_returned_reservation() -> None:
    observed = events()
    observed[1].pool_reserved = 128
    with pytest.raises(ValueError, match="returned-zero"):
        verify_leases(observed, 10, 128, IDENTITY)


def test_replacement_before_first_release_is_not_qualified() -> None:
    observed = events()
    observed[1], observed[2] = observed[2], observed[1]
    with pytest.raises(ValueError, match="sequence"):
        verify_leases(observed, 10, 128, IDENTITY)
