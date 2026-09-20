"""Command boundaries are independent of transport, GUI, and physical node count."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from contracts.commands import (CommandError, MAX_COMMAND_BYTES, command_topic, decode_command,
    decode_result, result_topic, target_rejection, validate_command, validate_result)

EXAMPLES = Path(__file__).resolve().parents[1] / 'contracts/examples'


def command():
    return json.loads((EXAMPLES / 'command.json').read_text())


def result():
    return json.loads((EXAMPLES / 'command-result.json').read_text())


def test_examples_and_cli_are_valid_without_executing_commands():
    request = command()
    assert decode_command(json.dumps(request).encode(), topic=command_topic(request['device_id'])) == request
    ack = result()
    assert decode_result(json.dumps(ack).encode(), topic=result_topic(ack['device_id'])) == ack
    run = subprocess.run([sys.executable, '-m', 'contracts.commands', str(EXAMPLES / 'command.json')],
                         capture_output=True, text=True)
    assert run.returncode == 0 and 'not sent or executed' in run.stdout


@pytest.mark.parametrize('field,value', [
    ('schema_version', '0.1'), ('command_id', 'not-a-uuid'), ('target_boot_id', 'old'),
    ('device_id', 'node/commands'), ('component_id', 'servo\n'), ('operation', 'toggle'),
    ('value', None), ('value', True), ('value', -1), ('value', 181), ('value', 1.5),
    ('value', float('nan')), ('observed_uptime_ms', -1), ('observed_uptime_ms', True),
    ('expires_uptime_ms', 500), ('expires_uptime_ms', 499), ('expires_uptime_ms', 60_501),
    ('expires_uptime_ms', 9007199254740992), ('admin', True),
])
def test_rejects_malformed_command(field, value):
    message = command()
    message[field] = value
    with pytest.raises(CommandError):
        validate_command(message)


def test_auto_has_no_setpoint_and_topic_matches_device():
    message = command()
    message.update(operation='auto', value=None)
    validate_command(message)
    message['value'] = 0
    with pytest.raises(CommandError):
        validate_command(message)
    for validate, message in [(validate_command, command()), (validate_result, result())]:
        with pytest.raises(CommandError):
            validate(message, topic='edgeguard/devices/other/commands')
    for builder in (command_topic, result_topic):
        with pytest.raises(CommandError):
            builder('node/extra')


@pytest.mark.parametrize('decoder', [decode_command, decode_result])
@pytest.mark.parametrize('payload', [b'{"a":1,"a":2}', b'{"value":NaN}', b'{"value":1e999}',
                                   b'\xff', b'null', b'[]', b'{', b'x' * (MAX_COMMAND_BYTES+1),
                                   b'[' * 2000 + b']' * 2000])
def test_bounded_strict_json(decoder, payload):
    with pytest.raises(CommandError):
        decoder(payload)


@pytest.mark.parametrize('status,reason,valid', [
    ('accepted', None, True), ('accepted', 'expired', False),
    ('rejected', 'expired', True), ('rejected', None, False),
    ('executed', None, False), ('rejected', 'made_up', False),
])
def test_result_does_not_claim_physical_execution(status, reason, valid):
    message = result()
    message.update(status=status, reason=reason)
    if valid:
        validate_result(message)
    else:
        with pytest.raises(CommandError):
            validate_result(message)
    message['measured_position'] = 110
    with pytest.raises(CommandError):
        validate_result(message)


def test_target_checks_use_node_capabilities_boot_and_local_uptime_without_side_effects():
    message = command()
    capabilities = {'servo_01': {'kind': 'servo', 'allowed_values': [0, 110]},
                    'lamp': {'kind': 'light', 'allowed_values': [0, 1]},
                    'fan': {'kind': 'fan', 'allowed_values': [0, 1]},
                    'sensor': {'kind': 'gas'}}
    original = deepcopy((message, capabilities))
    context = dict(device_id=message['device_id'], boot_id=message['target_boot_id'],
                   uptime_ms=700, capabilities=capabilities)
    assert target_rejection(message, **context) is None
    for changes, expected in [({'device_id': 'another_node'}, 'wrong_device'),
                              ({'boot_id': 'another_boot'}, 'wrong_boot'),
                              ({'uptime_ms': 499}, 'not_yet_valid'),
                              ({'uptime_ms': 5500}, 'expired')]:
        assert target_rejection(message, **{**context, **changes}) == expected
    assert target_rejection(message, **{**context, 'uptime_ms': 500}) is None
    assert target_rejection(message, **{**context, 'uptime_ms': 5499}) is None
    for changes, expected in [({'component_id': 'missing'}, 'unknown_component'),
                              ({'component_id': 'sensor'}, 'unsupported_operation'),
                              ({'value': 90}, 'value_out_of_range'),
                              ({'component_id': 'lamp'}, 'value_out_of_range'),
                              ({'operation': 'auto', 'value': None}, 'unsupported_operation'),
                              ({'component_id': 'fan', 'operation': 'auto', 'value': None}, None)]:
        assert target_rejection({**message, **changes}, **context) == expected
    assert (message, capabilities) == original
    with pytest.raises(ValueError):
        target_rejection(message, **{**context, 'uptime_ms': True})
