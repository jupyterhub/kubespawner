import json
import pathlib

import pytest
from test_utils import MockLogger

from kubespawner.events import BasicEventFormatter, RuleEventFormatter

RULE_TEST_FILES = (pathlib.Path(__file__).parent / "sample-events").glob(
    "*.events.json"
)
RULE_TEST_PARAMETERS = [
    (p, p.with_suffix("").with_suffix("").with_suffix(".messages.json"))
    for p in RULE_TEST_FILES
]


@pytest.mark.parametrize("events_path,messages_path", RULE_TEST_PARAMETERS)
def test_event_formatter_rules_builtin(events_path, messages_path):
    with open(events_path) as f:
        events = json.load(f)

    event_formatter = RuleEventFormatter()

    # Uncomment below to actually override the regression tests
    # formatted = [event_formatter.format_event(event) for event in events]
    # with open(messages_path, "w") as f:
    #     json.dump(formatted, f, indent=4)

    assert messages_path.exists()
    with open(messages_path) as f:
        messages = json.load(f)

    for event, message in zip(events, messages):
        rendered_message = event_formatter.format_event(event)
        assert rendered_message == message


def test_event_formatter_basic():
    event_formatter = BasicEventFormatter()
    event = {
        "kind": "Event",
        "involvedObject": {},
        "lastTimestamp": "2026-02-11T14:58:40Z",
        "type": "Warning",
        "reportingComponent": "component-one",
        "message": "something-went-wrong",
    }

    message = event_formatter.format_event(event)

    assert "something-went-wrong" in message


def test_event_formatter_rules_error():
    template_called = False

    def raises_exception():
        nonlocal template_called
        template_called = True

        raise RuntimeError

    logger = MockLogger()
    event_formatter = RuleEventFormatter(
        rules=[
            {
                "match": {"reportingComponent": ".*"},
                "template": raises_exception,
            }
        ],
        log=logger,
    )
    event = {
        "kind": "Event",
        "involvedObject": {},
        "lastTimestamp": "2026-02-11T14:58:40Z",
        "type": "Warning",
        "reportingComponent": "component-one",
        "message": "a-simple-message",
    }

    message = event_formatter.format_event(event)

    assert message == "a-simple-message"
    assert template_called
    assert logger.info_logs


def test_event_formatter_rules_error_template():
    logger = MockLogger()
    event_formatter = RuleEventFormatter(
        rules=[
            {
                "match": {"reportingComponent": ".*"},
                "template": "{no_such_group}",
            }
        ],
        log=logger,
    )
    event = {
        "kind": "Event",
        "involvedObject": {},
        "lastTimestamp": "2026-02-11T14:58:40Z",
        "type": "Warning",
        "reportingComponent": "component-one",
        "message": "a-simple-message",
    }

    message = event_formatter.format_event(event)

    assert message == "a-simple-message"
    assert logger.info_logs


def test_event_formatter_rules_extra_list_extend():
    rules = [
        {
            "match": {
                "reportingComponent": "component-one",
            },
            "template": "default-component-one",
        },
    ]
    extra_rules = [
        {
            "match": {
                "reportingComponent": "component-one",
            },
            "template": "extra-component-one",
        },
        {
            "match": {
                "reportingComponent": "component-two",
            },
            "template": "extra-component-two",
        },
    ]

    event_formatter = RuleEventFormatter(
        rules=rules,
        extra_rules=extra_rules,
    )
    event = {
        "kind": "Event",
        "involvedObject": {},
        "lastTimestamp": "2026-02-11T14:58:40Z",
        "type": "Warning",
        "reportingComponent": "component-one",
    }

    message = event_formatter.format_event(event)
    assert "default-component-one" in message

    event = {
        "kind": "Event",
        "involvedObject": {},
        "lastTimestamp": "2026-02-11T14:58:40Z",
        "type": "Warning",
        "reportingComponent": "component-two",
    }

    message = event_formatter.format_event(event)
    assert "extra-component-two" in message


def test_event_formatter_rules_extra_dict_extend():
    rules = {
        "first": {
            "match": {
                "reportingComponent": "component-one",
            },
            "template": "default-component-one",
        },
        "second": {
            "match": {
                "reportingComponent": "component-two",
            },
            "template": "default-component-two",
        },
    }
    extra_rules = {
        "first": {
            "match": {
                "reportingComponent": "component-one",
            },
            "template": "extra-component-one",
        },
        "third": {
            "match": {
                "reportingComponent": "component-two",
            },
            "template": "extra-component-two",
        },
    }

    event_formatter = RuleEventFormatter(
        rules=rules,
        extra_rules=extra_rules,
    )
    event = {
        "kind": "Event",
        "involvedObject": {},
        "type": "Warning",
        "lastTimestamp": "2026-02-11T14:58:40Z",
        "reportingComponent": "component-one",
    }

    message = event_formatter.format_event(event)

    assert "extra-component-one" in message
    event = {
        "kind": "Event",
        "involvedObject": {},
        "lastTimestamp": "2026-02-11T14:58:40Z",
        "type": "Warning",
        "reportingComponent": "component-two",
    }

    message = event_formatter.format_event(event)

    assert "default-component-two" in message
