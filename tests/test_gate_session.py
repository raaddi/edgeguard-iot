import hashlib
import json

import pytest

from ml.gate_evaluation import counterfactual_labels
from ml.gate_features import extract_features
from simulator.gate_pilot import simulate_session
from simulator.gate_session import GateSessionSettings


def test_default_pilot_output_is_unchanged():
    raw = json.dumps(simulate_session(seed=42, case="normal", run_id="compat"), sort_keys=True).encode()
    assert hashlib.sha256(raw).hexdigest() == "44070ec5e9c54bc72b8409c7a18b514236d47e044800c69147ad868da0844b72"


def test_custom_session_keeps_paired_parameters_and_labels_outside_features():
    settings = GateSessionSettings(duration_ms=30000, schedule=((2000, 110), (20000, 0)),
                                   stroke_bounds_ms=(1600, 2000), nominal_delays_ms=(250, 350))
    kwargs = dict(seed=12, run_id="custom", settings=settings)
    normal = simulate_session(case="normal", **kwargs)
    fault = simulate_session(case="command_delay", **kwargs)
    assert normal == simulate_session(case="normal", **kwargs)
    assert len(normal[0]) == 601 and normal[0][-1]["logical_ms"] == 30000
    assert fault[2]["config"]["stroke_ms"] == normal[2]["config"]["stroke_ms"]
    assert normal[2]["session_settings_version"] == "gate-session-settings-1"
    assert any(counterfactual_labels(*fault[:2], *normal[:2]))
    assert all("settings" not in r["x"] and "case" not in r["x"] for r in extract_features(*fault[:2]))


@pytest.mark.parametrize("kwargs", [
    {"duration_ms": 60001}, {"duration_ms": True}, {"stroke_bounds_ms": (1600, 900)},
    {"nominal_delays_ms": ()}, {"nominal_delays_ms": (49,)}, {"fault_delay_ms": 3000},
    {"schedule": ((950, 110),)}, {"schedule": ((1000, 1),)},
    {"schedule": ((1000, 110), (1000, 0))}, {"schedule": ((7900, 110),)},
])
def test_invalid_settings_are_rejected(kwargs):
    with pytest.raises(ValueError):
        GateSessionSettings(**kwargs)
