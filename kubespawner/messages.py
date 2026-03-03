import datetime
import re
from typing import Optional

# Anchored match patterns ^foo$
CONTAINER_FIELD_PATH_PAT = r"^spec\.(initContainers|containers)\{([^}]+)\}$"
USER_SCHEDULER_COMPONENT_PAT = r"^.*-user-scheduler$"
NODE_AFFINITY_FAILED_PAT = r"^Predicate NodeAffinity failed.*$"
CANCELLING_DELETION_MESSAGE_PAT = r"^Cancelling deletion of Pod.*$"
NODE_ASSIGNED_MESSAGE_PAT = r"^.*?assigned \S+ to (\S+)$"
IMAGE_MESSAGE_PAT = r'^.*image "([^"]+)".*$'


# reportingComponent is sometimes empty, as is source
def reporting_component(event: dict) -> str:
    return event["reportingComponent"] or event["source"]["component"]


def container_events_formatter(event: dict) -> Optional[str]:
    if reporting_component(event) != "kubelet":
        return

    involved_object = event["involvedObject"]

    try:
        field_path = involved_object["fieldPath"]
    except KeyError:
        return

    # Match the container paths and parse the container name
    match = re.match(CONTAINER_FIELD_PATH_PAT, field_path)
    if not match:
        return

    container_field, container = match.groups()

    # Switch on the reason for the event
    if event["reason"] in ("Started", "Killing", "Created", "Stopped"):
        return f"{event['reason']} the {container} container"
    elif event["reason"] in ("Pulling", "Pulled"):
        # Parse the image name
        image_match = re.match(IMAGE_MESSAGE_PAT, event["message"])
        if image_match is None:
            return
        image = image_match[1]

        return f"Pulling {image} image for the {container} container"


def pod_resource_events_formatter(event: dict) -> Optional[str]:
    if reporting_component(event) != "kubelet":
        return

    reason = event["reason"]

    if reason not in (
        "OutOfmemory",
        "OutOfcpu",
        "OutOfephemeral-storage",
        "OutOfpods",
    ):
        return

    resource = reason[len("OutOf") :]
    return f"The node selected to run your server ran out of {resource}"


def scheduler_events_formatter(event: dict) -> Optional[str]:
    if not re.match(USER_SCHEDULER_COMPONENT_PAT, reporting_component(event)):
        return

    if event["reason"] == "Scheduled":
        node_match = re.match(NODE_ASSIGNED_MESSAGE_PAT, event["message"])
        if node_match is None:
            return
        node = node_match[1]

        return f"A node ({node}) has been found to run your server"
    elif event["reason"] == "FailedScheduling":
        return "No existing nodes are currently able to run your server"


def gke_scheduler_events_formatter(event: dict) -> Optional[str]:
    if reporting_component(event) != "gke.io/optimize-utilization-scheduler":
        return

    if event["reason"] == "Scheduled":
        node_match = re.match(NODE_ASSIGNED_MESSAGE_PAT, event["message"])
        if node_match is None:
            return
        node = node_match[1]

        return f"A node ({node}) has been found to run your server"
    elif event["reason"] == "FailedScheduling":
        return "No existing nodes are currently able to run your server"


def cluster_autoscaler_events_formatter(event: dict) -> Optional[str]:
    if reporting_component(event) != "cluster-autoscaler":
        return

    if event["reason"] != "TriggeredScaleUp":
        return

    return "Launching new nodes by scaling up the cluster"


def node_affinity_events_formatter(event: dict) -> Optional[str]:
    if reporting_component(event) != "kubelet":
        return

    if event["reason"] != "NodeAffinity":
        return

    predicate_match = re.match(NODE_AFFINITY_FAILED_PAT, event["message"])
    if predicate_match is None:
        return

    return "It was not possible to find or launch any nodes to run your server. This is likely due to a configuration problem with the infrastructure or the JuyterHub"


def taint_eviction_events_formatter(event: dict) -> Optional[str]:
    if reporting_component(event) != "taint-eviction-controller":
        return

    if event["reason"] != "TaintManagerEviction":
        return

    predicate_match = re.match(CANCELLING_DELETION_MESSAGE_PAT, event["message"])
    if predicate_match is None:
        return

    return "Cancelling deletion of your server. This normally happens when a scale-up has just taken place."


DEFAULT_EVENT_FORMATTERS = [
    container_events_formatter,
    pod_resource_events_formatter,
    scheduler_events_formatter,
    gke_scheduler_events_formatter,
    cluster_autoscaler_events_formatter,
    node_affinity_events_formatter,
    taint_eviction_events_formatter,
]


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


def format_reflected_event(event: dict, formatters: list = None) -> str:
    """
    Format a Kubernetes Event object into a human-readable message.

    :ref: https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#event-v1-core
    """
    if formatters is None:
        formatters = DEFAULT_EVENT_FORMATTERS

    # Format each message into a bundle
    for formatter in formatters:
        message_body = formatter(event)
        if message_body is not None:
            break
    else:
        message_body = event["message"]

    # Render rich and plain-text representations
    message = format_plain_message(message_body, event)
    html_message = format_html_message(message_body, event)

    return {"message": message, "html_message": html_message}


if __name__ == "__main__":
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "file", type=argparse.FileType("r"), help="Path to JSON array of Event objects"
    )
    parser.add_argument("--json", help="Output as JSON", action="store_true")
    parser.add_argument(
        "--no-pretty", help="Do not pretty-print the events", action="store_true"
    )

    args = parser.parse_args()

    events = json.load(args.file)
    formatters = [] if args.no_pretty else None

    bundles = [format_reflected_event(event, formatters) for event in events]

    if args.json:
        json.dump(bundles, sys.stdout)
    else:
        for bundle in bundles:
            print(bundle["message"])
