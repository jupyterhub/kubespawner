# Inspired by, and based on, Adam Tilghman's Multi-Namespace work in
#  https://github.com/jupyterhub/kubespawner/pull/218
import datetime
import time
from kubernetes import watch
from .reflector import NamespacedResourceReflector
from traitlets import Bool
# This is kubernetes client implementation specific, but we need to know
# whether it was a network or watch timeout.
from urllib3.exceptions import ReadTimeoutError


class MultiNamespaceResourceReflector(NamespacedResourceReflector):
    list_method_omit_namespace = Bool(
        False,
        help="""
        If True, our calls to API `list_method_name` will omit a `namespace`
        argument.  Necessary for non-namespaced methods such as
        `list_pod_for_all_namespaces`
        """
    )

    def _create_resource_key(self, resource):
        """Maps a Kubernetes resource object onto a hashable Dict key;
        subclass may override if `resource.metadata.name` is not
        unique (e.g. pods across multiple namespaces)
        """
        return resource.metadata.name

    def _list_and_update(self):
        """
        Update current list of resources by doing a full fetch.

        Overwrites all current resource info.
        """
        initial_resources = getattr(self.api, self.list_method_name)(
            label_selector=self.label_selector,
            field_selector=self.field_selector,
            _request_timeout=self.request_timeout,
        )
        if not self.list_method_omit_namespace:
            initial_resources['namespace'] = self.namespace
        # This is an atomic operation on the dictionary!
        self.resources = {
            self._create_resource_key(p): p for p in initial_resources.items}
        # return the resource version so we can hook up a watch
        return initial_resources.metadata.resource_version

    def _watch_and_update(self):
        """
        Keeps the current list of resources up-to-date

        This method is to be run not on the main thread!

        We first fetch the list of current resources, and store that. Then we
        register to be notified of changes to those resources, and keep our
        local store up-to-date based on these notifications.

        We also perform exponential backoff, giving up after we hit 32s
        wait time. This should protect against network connections dropping
        and intermittent unavailability of the api-server. Every time we
        recover from an exception we also do a full fetch, to pick up
        changes that might've been missed in the time we were not doing
        a watch.

        Note that we're playing a bit with fire here, by updating a dictionary
        in this thread while it is probably being read in another thread
        without using locks! However, dictionary access itself is atomic,
        and as long as we don't try to mutate them (do a 'fetch / modify /
        update' cycle on them), we should be ok!
        """
        selectors = []
        log_name = ""
        if self.label_selector:
            selectors.append("label selector=%r" % self.label_selector)
        if self.field_selector:
            selectors.append("field selector=%r" % self.field_selector)
        log_selector = ', '.join(selectors)

        cur_delay = 0.1
        ns = self.namespace
        if self.list_method_omit_namespace:
            ns = "[GLOBAL]"
        self.log.info(
            "watching for %s with %s in namespace %s",
            self.kind, log_selector, ns,
        )
        while True:
            self.log.debug("Connecting %s watcher", self.kind)
            start = time.monotonic()
            w = watch.Watch()
            try:
                resource_version = self._list_and_update()
                if not self.first_load_future.done():
                    # signal that we've loaded our initial data
                    self.first_load_future.set_result(None)
                watch_args = {
                    'label_selector': self.label_selector,
                    'field_selector': self.field_selector,
                    'resource_version': resource_version,
                }
                if not self.list_method_omit_namespace:
                    watch_args['namespace'] = self.namespace
                if self.request_timeout:
                    # set network receive timeout
                    watch_args['_request_timeout'] = self.request_timeout
                if self.timeout_seconds:
                    # set watch timeout
                    watch_args['timeout_seconds'] = self.timeout_seconds
                # in case of timeout_seconds, the w.stream just exits (no exception thrown)
                # -> we stop the watcher and start a new one
                for watch_event in w.stream(
                    getattr(self.api, self.list_method_name),
                    **watch_args
                ):
                    # Remember that these events are k8s api related WatchEvents
                    # objects, not k8s Event or Pod representations, they will
                    # reside in the WatchEvent's object field depending on what
                    # kind of resource is watched.
                    #
                    # ref: https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.16/#watchevent-v1-meta
                    # ref: https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.16/#event-v1-core
                    cur_delay = 0.1
                    resource = watch_event['object']
                    r_key = self._create_resource_key(resource)
                    if watch_event['type'] == 'DELETED':
                        # This is an atomic delete operation on the dictionary!
                        self.log.debug(
                            "Removing {} from {} watcher.".format(
                                r_key, self.kind))
                        self.resources.pop(r_key, None)
                    else:
                        # This is an atomic operation on the dictionary!
                        self.log.debug(
                            "Adding {} to {} watcher.".format(
                                r_key, self.kind))
                        self.resources[r_key] = resource
                    if self._stop_event.is_set():
                        self.log.info("%s watcher stopped", self.kind)
                        break
                    watch_duration = time.monotonic() - start
                    if watch_duration >= self.restart_seconds:
                        self.log.debug(
                            "Restarting %s watcher after %i seconds",
                            self.kind, watch_duration,
                        )
                        break
            except ReadTimeoutError:
                # network read time out, just continue and restart the watch
                # this could be due to a network problem or just low activity
                self.log.warning(
                    "Read timeout watching %s, reconnecting", self.kind)
                continue
            except Exception:
                cur_delay = cur_delay * 2
                if cur_delay > 30:
                    self.log.exception(
                        "Watching resources never recovered, giving up")
                    if self.on_failure:
                        self.on_failure()
                    return
                self.log.exception(
                    "Error when watching resources, retrying in %ss", cur_delay)
                time.sleep(cur_delay)
                continue
            else:
                # no events on watch, reconnect
                self.log.debug("%s watcher timeout", self.kind)
            finally:
                w.stop()
                if self._stop_event.is_set():
                    self.log.info("%s watcher stopped", self.kind)
                    break
        self.log.warning("%s watcher finished", self.kind)


class PodReflector(MultiNamespaceResourceReflector):
    kind = 'pods'
    # FUTURE: These labels are the selection labels for the PodReflector. We
    # might want to support multiple deployments in the same namespace, so we
    # would need to select based on additional labels such as `app` and
    # `release`.
    labels = {
        'component': 'singleuser-server',
    }

    list_method_name = 'list_namespaced_pod'

    @property
    def pods(self):
        return self.resources


class MultiNamespacePodReflector(PodReflector):
    list_method_name = 'list_pod_for_all_namespaces'
    list_method_omit_namespace = True

    def _create_resource_key(self, resource):
        return "{}/{}".format(resource.metadata.namespace,
                              resource.metadata.name)


class EventReflector(MultiNamespaceResourceReflector):
    """
    EventsReflector is merely a configured NamespacedResourceReflector. It
    exposes the events property, which is simply mapping to self.resources where
    the NamespacedResourceReflector keeps an updated list of the resource
    defined by the `kind` field and the `list_method_name` field.
    """
    kind = 'events'
    list_method_name = 'list_namespaced_event'

    @property
    def events(self):
        """
        Returns list of the python kubernetes client's representation of k8s
        events within the namespace, sorted by the latest event.

        ref: https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.16/#event-v1-core
        """

        # NOTE:
        # - self.resources is a dictionary with keys mapping unique ids of
        #   Kubernetes Event resources, updated by NamespacedResourceReflector.
        #   self.resources will builds up with incoming k8s events, but can also
        #   suddenly refreshes itself entirely. We should not assume a call to
        #   this dictionary's values will result in a consistently ordered list,
        #   so we sort it to get it somewhat more structured.
        # - We either seem to get only event.last_timestamp or event.event_time,
        #   both fields serve the same role but the former is a low resolution
        #   timestamp without and the other is a higher resolution timestamp.
        #
        # - We also inject the epoch as a fallback last-resort time
        return sorted(
            self.resources.values(),
            key=lambda event: (event.last_timestamp or event.event_time or
                               datetime.datetime.utcfromtimestamp(0),)
        )


class MultiNamespaceEventReflector(EventReflector):
    list_method_name = 'list_event_for_all_namespaces'
    list_method_omit_namespace = True
