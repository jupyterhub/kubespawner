"""
Class for formatting Kubernetes event messages.
"""

import datetime
import re
from typing import Optional, Tuple

from traitlets import (
    Dict,
    List,
    TraitError,
    Union,
    default,
    observe,
    validate,
)
from traitlets.config import LoggingConfigurable

from .utils import sorted_dict_values


class EventFormatter(LoggingConfigurable):
    def format_event(self, event: dict) -> str:
        """
        Format a Kubernetes Event into a string
        :ref: https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#event-v1-core
        """


class BasicEventFormatter(EventFormatter):
    def format_event(self, event: dict) -> str:
        return event["message"]


class RuleEventFormatter(EventFormatter):
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

    rules = Union(
        trait_types=[
            List(),
            Dict(),
        ],
        config=True,
        help="""
        List or dictionary of event formatter rules.

        A "rule" is an object that consists of two required fields:

        - `match` — an object containing regular expression patterns (strings or compiled regular expressions) that match similarly named `Event` fields. Any named capture groups will be made available to the `template`. Supported fields are `reportingComponent`, `fieldPath`, `reason`, `message`, and `type`.
        - `template` — a string, or a callable that will be used to build a formatted event message. If a string, the `.format` method will be invoked with any named capture group results as keyword arguments. If a callable, the same named capture groups will be directly passed as keyword arguments. Missing named capture groups are provided as empty strings.

        If provided as a list, each item should be an aforementioned "rule" object.
        If provided as a dictionary, the keys can be any descriptive name and the values should be the aforementioned "rule" objects.
        The items will be sorted lexicographically by the dictionary keys, and the sorted values will be used to build the list of rules.
        .. admonition:: Example
           :collapsible: closed

           Here is an example of two rules that are defined by default in the `RuleEventFormatter`.

           .. code-block:: python

              c.RuleEventFormatter.rules = 
                [
                    {
                        "match": {
                            "reportingComponent": r"kubelet",
                            "fieldPath": r"spec\.(initContainers|containers)\{(?P<container>[^}]+)\}",
                            "reason": r"(?P<action>Pulling|Pulled)",
                            "message": r'.*image\s*"(?P<image>[^"]+)\:(?P<tag>[^"]+)"',
                        },
                        "template": "{action} image {image}:{tag} for the {container} container",
                    },
                    {
                        "match": {
                            "reportingComponent": r"kubelet",
                            "fieldPath": r"spec\.(initContainers|containers)\{(?P<container>[^}]+)\}",
                            "reason": r"(?P<action>Started|Killing|Created|Stopped)",
                        },
                        "template": '{action} the container "{container}"',
                    }
                ]
                
        When set to none, a default ruleset is used.

        :ref: https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#event-v1-core
        """,
    )

    extra_rules = Union(
        trait_types=[
            List(),
            Dict(),
        ],
        config=True,
        help="""
        List or dictionary of additional event formatter rules on top of :attr:`.RuleEventFormatter.rules`.
        These rules are merged with :attr:`.RuleEventFormatter.rules`. Where `extra_rules` is a dict, the name of each rule can be chosen to override a base rule. 

        .. seealso::

          :attr:`.RuleEventFormatter.rules` for information on fields available in template strings.
        """,
    )

    @default("rules")
    def _default_rules(self):
        return [
            {
                "match": {
                    "reportingComponent": r"kubelet",
                    "fieldPath": r"spec\.(initContainers|containers)\{(?P<container>[^}]+)\}",
                    "reason": r"(?P<action>Pulling|Pulled)",
                    "message": r'.*image\s*"(?P<image>[^"]+)\:(?P<tag>[^"]+)"',
                },
                "template": "{action} image {image}:{tag} for the {container} container",
            },
            {
                "match": {
                    "reportingComponent": r"kubelet",
                    "fieldPath": r"spec\.(initContainers|containers)\{(?P<container>[^}]+)\}",
                    "reason": r"(?P<action>Started|Killing|Created|Stopped)",
                },
                "template": '{action} the container "{container}"',
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
                "template": "Canceling deletion of your server. This normally happens when a scale-up has just taken place",
            },
            {
                "match": {
                    "reportingComponent": r"kubelet",
                    "reason": r"BackOff",
                    "fieldPath": r"spec\.(initContainers|containers)\{(?P<container>[^}]+)\}",
                    "message": r'Back-off pulling image "(?P<image>[^"]+)\:(?P<tag>[^"]+)"',
                },
                "template": 'Waiting to try pulling {image}:{tag} for the container "{container}" after the last attempt failed',
            },
            {
                "match": {
                    "reportingComponent": r"kubelet",
                    "reason": r"Failed",
                    "fieldPath": r"spec\.(initContainers|containers)\{(?P<container>[^}]+)\}",
                    "message": r'Failed to pull image "(?P<image>[^"]+)\:(?P<tag>[^"]+)"',
                },
                "template": 'Attempts to pull {image}:{tag} for the container "{container}" failed',
            },
            {
                "match": {
                    "reportingComponent": r"kubelet",
                    "reason": r"Failed",
                    "fieldPath": r"spec\.(initContainers|containers)\{(?P<container>[^}]+)\}",
                    "message": r"Error: ImagePullBackOff",
                },
                "template": 'Waiting to try pulling an image into the container "{container}"',
            },
            {
                "match": {
                    "reportingComponent": r"kubelet",
                    "reason": r"Failed",
                    "fieldPath": r"spec\.(initContainers|containers)\{(?P<container>[^}]+)\}",
                    "message": r"Error: ErrImagePull",
                },
                "template": 'Attempts to pull an image for the container "{container}" failed',
            },
        ]

    @validate("rules", "extra_rules")
    def _validate_rules(self, proposal: dict):
        def validate_match(match: dict):
            # Check required fields
            if "reportingComponent" not in match:
                raise TraitError(
                    "rule['match'] missing required key 'reportingComponent'"
                )

            # Check types of fields
            allowed_match_fields = (
                "reportingComponent",
                "fieldPath",
                "reason",
                "message",
                "type",
            )

            # Prohibit unknown fields
            unknown_match_fields = match.keys() - allowed_match_fields
            if unknown_match_fields:
                raise TraitError(
                    f"rule['match'] contains unknown key(s): {', '.join(unknown_match_fields)}"
                )

            # Validate known fields
            known_match_fields = allowed_match_fields & match.keys()
            for field in known_match_fields:
                value = match[field]

                if not isinstance(value, (str, re.Pattern)):
                    raise TraitError(
                        f"rule['match'][{field!r}] must be string or compiled regular expression"
                    )

        def validate_template(template: any):
            if not (isinstance(template, str) or callable(template)):
                raise TraitError("rule['template'] must be a string or callable")

        def validate_rule(rule: dict):
            # Check rule required fields
            for required_field in ("match", "template"):
                if required_field not in rule:
                    raise TraitError(f"rule missing required key '{required_field}'")

            validate_match(rule["match"])
            validate_template(rule["template"])
            return rule

        if isinstance(proposal["value"], list):
            return [validate_rule(rule) for rule in proposal["value"]]
        else:
            return {
                name: validate_rule(rule) for name, rule in proposal["value"].items()
            }

    _compiled_rules = None

    @observe("rules", "extra_rules")
    def _event_formatter_rules_changed(self, change: dict):
        # Clear compiled event formatter rules
        self._compiled_rules = None

    @property
    def compiled_rules(self):
        if self._compiled_rules is None:
            # Template for forming helpful debug messages, by keeping track
            # of where rule came from
            trait_path_template = "{}[{!r}]"

            # Merge (in order) the given rulesets
            merged_rules = {}
            for i, rules_name in enumerate(("rules", "extra_rules")):
                rules = getattr(self, rules_name)

                if isinstance(rules, list):
                    # NOTE: the rules index i must not exceed 9, as it is
                    #       expected to be a single char
                    compiled_rules = {
                        # Ensure that names sort by ruleset index
                        f"{i}-{rules_name}-{j}": (
                            rule,
                            trait_path_template.format(rules_name, j),
                        )
                        for j, rule in enumerate(rules)
                    }
                else:
                    compiled_rules = {
                        name: (rule, trait_path_template.format(rules_name, name))
                        for name, rule in rules.items()
                    }
                merged_rules.update(compiled_rules)

            # List entries are merged without cloberring, whereas dict values may clobber one another
            # Sort by unique ID
            self._compiled_rules = sorted_dict_values(merged_rules)

        # Always append a fallback rule
        self._compiled_rules.append(
            (self.FALLBACK_EVENT_RULE, self.FALLBACK_EVENT_RULE_ID)
        )
        return self._compiled_rules

    def _normalize_kubernetes_event(self, event: dict) -> dict:
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
            "type": event["type"],
        }

    def _single_rule_matches(self, rule: dict, match_source: dict) -> Optional[dict]:
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
        self,
        event: dict,
    ) -> Tuple[dict, str, dict]:
        """
        Match a Kubernetes event against a list of formatter rules.
        If no given rules match, match against a catch-all rule.
        """
        match_source = self._normalize_kubernetes_event(event)

        # Try to match a rule
        for rule, rule_id in self.compiled_rules:
            matches = self._single_rule_matches(rule, match_source)
            if matches is not None:
                return rule, rule_id, matches

        # We should have encountered a final fallback rule
        assert False, "The fallback event rule should match any event"

    def format_event(self, event: dict) -> str:
        rule, rule_path, matches = self.match_event_rule(event)
        template = rule["template"]

        if isinstance(template, str):
            format_template = template.format
        else:
            format_template = template

        try:
            return format_template(**matches)
        except Exception:
            self.log.exception(
                f"Event template for rule {rule_path} failed to render successfully."
            )
            return event["message"]


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


def decorate_plain_message(message: str, event: dict) -> str:
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

    # Trim the time to the nearest second, assume UTC
    timestamp = moment.strftime("%Y-%m-%dT%H:%M:%SZ")

    return f"{timestamp}{icon}{message}"


def decorate_html_message(message: str, event: dict) -> str:
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

    # Trim the time to the nearest second, assume UTC
    if event["lastTimestamp"]:
        moment = parse_timestamp(event["lastTimestamp"])
    else:
        moment = parse_micro_timestamp(event["eventTime"])

    # Compute both true isoformat string and seconds-resolution readable string
    readable_time = moment.strftime("%Y-%m-%dT%H:%M:%SZ")
    true_time = moment.isoformat()

    timestamp = f'<span class="badge bg-light-subtle text-light-emphasis rounded-pill"><time datetime="{true_time}">{readable_time}</time></span>'

    return f"{timestamp}{icon}{message}"
