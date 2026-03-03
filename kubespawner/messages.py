import re

# Anchored match patterns ^foo$
CONTAINER_FIELD_PATH_PAT = r"^spec\.(initContainers|containers)\{([^}]+)\}$"
USER_SCHEDULER_COMPONENT_PAT = r"^.*-user-scheduler$"
NODE_ASSIGNED_MESSAGE_PAT = r"^.*?assigned \S+ to (\S+)$"
NODE_AFFINITY_FAILED_PAT = r"^Predicate NodeAffinity failed.*$"
CANCELLING_DELETION_MESSAGE_PAT = r"^Cancelling deletion of Pod.*$"
IMAGE_MESSAGE_PAT = r'^.*image "([^"]+)".*$'


def container_events(event: dict) -> str | None:
    if event["reportingComponent"] != "kubelet":
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


def pod_resource_events(event: dict) -> str | None:
    if event["reportingComponent"] != "kubelet":
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


def scheduler_events(event: dict) -> str | None:
    if not re.match(USER_SCHEDULER_COMPONENT_PAT, event["reportingComponent"]):
        return

    if event["reason"] == "Scheduled":
        node_match = re.match(NODE_ASSIGNED_MESSAGE_PAT, event["message"])
        if node_match is None:
            return
        node = node_match[1]

        return f"A node ({node}) has been found to run your server"
    elif event["reason"] == "FailedScheduling":
        return "No existing nodes are currently able to run your server"


def gke_scheduler_events(event: dict) -> str | None:
    if event["reportingComponent"] != "gke.io/optimize-utilization-scheduler":
        return

    if event["reason"] == "Scheduled":
        node_match = re.match(NODE_ASSIGNED_MESSAGE_PAT, event["message"])
        if node_match is None:
            return
        node = node_match[1]

        return f"A node ({node}) has been found to run your server"
    elif event["reason"] == "FailedScheduling":
        return "No existing nodes are currently able to run your server"


def cluster_autoscaler_events(event: dict) -> str | None:
    if event["reportingComponent"] != "cluster-autoscaler":
        return

    if event["reason"] != "TriggeredScaleUp":
        return

    return "Launching new nodes by scaling up the cluster"


def node_affinity_events(event: dict) -> str | None:
    if event["reportingComponent"] != "kubelet":
        return

    if event["reason"] != "NodeAffinity":
        return

    predicate_match = re.match(NODE_AFFINITY_FAILED_PAT, event["message"])
    if predicate_match is None:
        return

    return "It was not possible to find or launch any nodes to run your server. This is likely due to a configuration problem with the infrastructure or the JuyterHub"


def taint_eviction_events(event: dict) -> str | None:
    if event["reportingComponent"] != "taint-eviction-controller":
        return

    if event["reason"] != "TaintManagerEviction":
        return

    predicate_match = re.match(NODE_AFFINITY_FAILED_PAT, event["message"])
    if predicate_match is None:
        return

    return "It was not possible to find or launch any nodes to run your server. This is likely due to a configuration problem with the infrastructure or the JuyterHub"


event_formatters = [
    container_events,
    pod_resource_events,
    scheduler_events,
    gke_scheduler_events,
    cluster_autoscaler_events,
    node_affinity_events,
]


def format_reflected_event(event: dict) -> str:
    """
    Format a Kubernetes Event object into a human-readable message.

    :ref: https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.28/#event-v1-core
    """
    for formatter in event_formatters:
        result = formatter(event)
        if result is not None:
            return result

    return "{} [{}] {}".format(
        event["lastTimestamp"] or event["eventTime"],
        event["type"],
        event["message"],
    )


if __name__ == "__main__":
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "file", type=argparse.FileType("r"), help="Path to JSON array of Event objects"
    )
    parser.add_argument("--json", help="Output as JSON", action="store_true")

    args = parser.parse_args()

    events = json.load(args.file)
    messages = [format_reflected_event(event) for event in events]
    if args.json:
        json.dump(messages, sys.stdout)
    else:
        print("\n".join(messages))
