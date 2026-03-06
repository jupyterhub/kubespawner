import datetime


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
