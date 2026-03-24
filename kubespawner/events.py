from typing import Optional, Tuple

import datetime
import re


# A simple message-based event rule.
# Matches everything
FALLBACK_EVENT_RULE_ID = "<fallback>"
FALLBACK_EVENT_RULE = {
    "match": {
        "reportingComponent": ".*",
        "message": "(?P<text>.*)",
    },
    "template": "{text}",
}


DEFAULT_EVENT_RULES = [
    {
        "match": {
            "reportingComponent": r"kubelet",
            "fieldPath": r"spec\.(initContainers|containers)\{(?P<container>[^}]+)\}",
            "reason": r"(?P<action>Pulling|Pulled)",
            "message": r'.*image\s*"(?P<image>[^"]+)\:(?P<tag>[^"]+)"',
        },
        "template": "{action} {image} image ({tag}) for the {container} container",
    },
    {
        "match": {
            "reportingComponent": r"kubelet",
            "fieldPath": r"spec\.(initContainers|containers)\{(?P<container>[^}]+)\}",
            "reason": r"(?P<action>Started|Killing|Created|Stopped)",
        },
        "template": "{action} the {container} container",
    },
    {
        "match": {
            "reportingComponent": r"kubelet",
            "reason": r"OutOf(?P<resource>memory|cpu|ephemeral-storage|pods)",
        },
        "template": "The node selected to run your server ran out of {resource}",
    },
    {
        "match": {
            "reportingComponent": r"(.*-)?(user|default)-scheduler",
            "reason": r"Scheduled",
            "message": r".*?assigned \S+ to (?P<node>\S+)",
        },
        "template": "A node ({node}) has been found to run your server",
    },
    {
        "match": {
            "reportingComponent": r"(.*-)?(user|default)-scheduler",
            "reason": r"FailedScheduling",
        },
        "template": "No existing nodes are currently able to run your server",
    },
    {
        "match": {
            "reportingComponent": r"cluster-autoscaler",
            "reason": r"TriggeredScaleUp",
        },
        "template": "Launching new nodes by scaling up the cluster",
    },
    {
        "match": {
            "reportingComponent": r"kubelet",
            "message": r"Predicate NodeAffinity failed.*",
            "reason": "NodeAffinity",
        },
        "template": "It was not possible to find or launch any nodes to run your server. This is likely due to a configuration problem with the infrastructure or the JupyterHub",
    },
    {
        "match": {
            "reportingComponent": r"gke\.io/optimize-utilization-scheduler",
            "reason": r"Scheduled",
            "message": r".*?assigned \S+ to (?P<node>\S+)",
        },
        "template": "A node ({node}) has been found to run your server",
    },
    {
        "match": {
            "reportingComponent": r"gke\.io/optimize-utilization-scheduler",
            "reason": r"FailedScheduling",
        },
        "template": "No existing nodes are currently able to run your server",
    },
    {
        "match": {
            "reportingComponent": r"taint-eviction-controller",
            "reason": r"TaintManagerEviction",
            "message": r"Cancelling deletion of Pod.*",
        },
        "template": "Cancelling deletion of your server. This normally happens when a scale-up has just taken place.",
    },
]


def normalize_kubernetes_event(self, event: dict) -> dict:
    """
    Normalise event to handle reportingComponent <-> source.component
    Fields can both be missing (optional) and in-practice also empty strings
    We normalise missing or "" to ""
    """
    return {
        "fieldPath": event["involvedObject"].get("fieldPath") or "",
        "reportingComponent": event.get("reportingComponent")
        or event.get("source", {}).get("component")
        or "",
        "message": event.get("message") or "",
        "reason": event.get("reason") or "",
    }


def single_rule_matches(rule: dict, match_source: dict) -> Optional[dict]:
    """
    Match a normalised event against a list of formatter rules.
    If a match is found, return the match dictionary.
    """
    matches = {}
    for field, pattern in rule["match"].items():
        # Pull out the value for the match field
        value = match_source[field]

        # The event value must match the rule value
        match = re.match(pattern, value or "")
        if match is None:
            return None

        # Include matches for groups, where optional groups default to ""
        matches.update(match.groupdict(default=""))
    return matches


def match_event_rule(
    event: dict,
    compiled_rules: list,
) -> Tuple[dict, str, dict]:
    """
    Match a Kubernetes event against a list of formatter rules.
    If no given rules match, match against a catch-all rule.
    """
    match_source = normalize_kubernetes_event(event)

    # Try to match a rule
    for rule, rule_id in compiled_rules:
        matches = single_rule_matches(rule, match_source)
        if matches is not None:
            return rule, rule_id, matches

    # Fall back on catch-all rule
    matches = single_rule_matches(FALLBACK_EVENT_RULE, match_source)
    assert matches is not None, "The fallback event rule should match any event"

    return rule, FALLBACK_EVENT_RULE_ID, matches


def parse_micro_timestamp(time: str) -> datetime.datetime:
    """
    Parse a MicroTime timestamp into a UTC datetime.

    :ref: https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#event-v1-core
    """
    return datetime.datetime.strptime(time, "%Y-%m-%dT%H:%M:%S.%f%z").astimezone(
        datetime.timezone.utc
    )


def parse_timestamp(time: str) -> datetime.datetime:
    """
    Parse a Time timestamp into a UTC datetime.

    :ref: https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#event-v1-core
    """

    return datetime.datetime.strptime(time, "%Y-%m-%dT%H:%M:%S%z").astimezone(
        datetime.timezone.utc
    )


def format_plain_message(message: str, event: dict) -> str:
    """
    Build a plain-text message from a plain-text message body and an Event object.

    :ref: https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#event-v1-core
    """
    event_type = event["type"]

    if event_type == "Warning":
        icon = " ⚠️ "
    elif event_type == "Normal":
        icon = " ℹ️ "
    else:
        icon = " "

    if event["lastTimestamp"]:
        moment = parse_timestamp(event["lastTimestamp"])
    else:
        moment = parse_micro_timestamp(event["eventTime"])

    # Trim the time to the nearest section, assume UTC
    timestamp = moment.strftime("%Y-%m-%dT%H:%M:%SZ")

    return f"{timestamp}{icon}{message}"


def format_html_message(message: str, event: dict) -> str:
    """
    Build a full HTML message from a plain-text message body and an Event object.

    :ref: https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#event-v1-core
    """
    event_type = event["type"]

    if event_type == "Warning":
        icon = ' <span class="badge bg-warning-subtle text-warning-emphasis rounded-pill">Warning</span> '
    elif event_type == "Normal":
        icon = ' <span class="badge bg-info-subtle text-info-emphasis rounded-pill">Info</span> '
    else:
        icon = " "

    # Trim the time to the nearest section, assume UTC
    if event["lastTimestamp"]:
        moment = parse_timestamp(event["lastTimestamp"])
    else:
        moment = parse_micro_timestamp(event["eventTime"])

    # Compute both true isoformat string and seconds-resolution readable string
    readable_time = moment.strftime("%Y-%m-%dT%H:%M:%SZ")
    true_time = moment.isoformat()

    timestamp = f'<span class="badge bg-light-subtle text-light-emphasis rounded-pill"><time datetime="{true_time}">{readable_time}</time></span>'

    return f"{timestamp}{icon}{message}"
