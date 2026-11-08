"""Checks the Umbaji Monitoring Standard contract rules.

Plain script, in the style of the other checks in this project, so it needs no
test dependency:

    python -m monitoring.contract_check

Only the pure contract logic is covered here. The probes themselves touch the
database and the filesystem, so they are exercised by calling the endpoint on a
running instance.
"""

import asyncio

from monitoring.contract import (
    CONTRACT_VERSION,
    Indicator,
    Probe,
    ProbeOutcome,
    Threshold,
    roll_up_status,
    run_probe,
    status_from_threshold,
)


def check(label, actual, expected):
    assert actual == expected, f"{label}: expected {expected!r}, got {actual!r}"
    print(f"  ok  {label}")


def test_roll_up():
    print("roll-up")
    check(
        "a critical component down takes the service down",
        roll_up_status([{"critical": True, "status": "down"}], []),
        "down",
    )
    # Losing a non-critical dependency hurts, it does not stop the service.
    check(
        "a non-critical component down only degrades",
        roll_up_status([{"critical": False, "status": "down"}], []),
        "degraded",
    )
    # A probe that silently stopped running would otherwise leave the service
    # looking healthy forever.
    check(
        "an unknown never passes for healthy",
        roll_up_status([{"critical": False, "status": "unknown"}], []),
        "degraded",
    )
    check(
        "an indicator can degrade the service",
        roll_up_status([], [{"status": "degraded"}]),
        "degraded",
    )
    check("everything up is up", roll_up_status([{"critical": True, "status": "up"}], []), "up")
    check("an empty report is up, not unknown", roll_up_status([], []), "up")


def test_thresholds():
    print("thresholds")
    t = Threshold(warning=0.05, critical=0.15)
    check("below warning", status_from_threshold(0.01, t), "up")
    check("at warning", status_from_threshold(0.05, t), "degraded")
    check("at critical", status_from_threshold(0.15, t), "down")
    check("a missing value is unknown, never up", status_from_threshold(None, t), "unknown")
    check("no threshold means nothing to grade", status_from_threshold(42, None), "up")
    check(
        "an indicator derives its own status",
        Indicator("k", "K", None, "count", t).status,
        "unknown",
    )


async def _timeout_and_error():
    print("probe deadline")

    async def hangs():
        await asyncio.sleep(30)
        return ProbeOutcome("up")

    # A monitoring endpoint that can hang is a liability: it will hang exactly
    # when the incident starts.
    result = await run_probe(Probe("x", "X", "database", True, hangs), 0.2)
    check("a hanging probe is abandoned", result["status"], "unknown")
    assert "timed out" in result["message"]
    print("  ok  the reason says it timed out")

    async def boom():
        raise RuntimeError("connect ECONNREFUSED 10.0.0.4:5432")

    result = await run_probe(Probe("y", "Y", "database", True, boom), 1)
    check("a raising probe is reported, not propagated", result["status"], "down")
    # The raw error can carry a host or a credential; it belongs in our logs.
    assert "10.0.0.4" not in str(result), "the probe leaked a host into the response"
    print("  ok  the raw error stays out of the response")


def main():
    print(f"Umbaji Monitoring Standard {CONTRACT_VERSION}")
    test_roll_up()
    test_thresholds()
    asyncio.run(_timeout_and_error())
    print("All contract checks passed.")


if __name__ == "__main__":
    main()
