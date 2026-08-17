"""Deterministic event bus.

Events are how mechanics react to each other without knowing about each
other -- e.g. `damage_teleport` in v1 was hardcoded into the damage path;
in v2 it is an ability that subscribes to "actor.damaged".

Ordering is strictly FIFO within a tick and handlers are called in
registration order, so replay is reproducible.  Events raised during
dispatch are queued for the NEXT drain, never appended mid-iteration --
this prevents the unbounded-recursion class of bug and keeps tick cost
predictable.
"""

__all__ = ["EventBus", "Event"]


class Event:
    __slots__ = ("name", "data", "tick")

    def __init__(self, name, data=None, tick=0):
        self.name = name
        self.data = data or {}
        self.tick = tick

    def get(self, key, default=None):
        return self.data.get(key, default)

    def __repr__(self):
        return "Event(%s t%d %s)" % (self.name, self.tick, self.data)


class EventBus:
    __slots__ = ("_subs", "_queue", "_next", "log", "log_enabled", "_depth")

    MAX_DRAIN_PASSES = 8

    def __init__(self, log_enabled=False):
        self._subs = {}      # name -> [handler, ...] in registration order
        self._queue = []
        self._next = []
        self.log = []
        self.log_enabled = log_enabled
        self._depth = 0

    # ---- subscription ---------------------------------------------
    def on(self, name, handler):
        self._subs.setdefault(name, []).append(handler)
        return handler

    def off(self, name, handler):
        lst = self._subs.get(name)
        if lst and handler in lst:
            lst.remove(handler)

    # ---- emission -------------------------------------------------
    def emit(self, name, tick=0, **data):
        ev = Event(name, data, tick)
        if self._depth:
            self._next.append(ev)
        else:
            self._queue.append(ev)
        if self.log_enabled:
            self.log.append(ev)
        return ev

    def drain(self):
        """Dispatch all queued events.  Returns the number dispatched.

        Events emitted by handlers are deferred to the next pass, and passes
        are capped, so a feedback loop degrades instead of hanging."""
        total = 0
        for _ in range(self.MAX_DRAIN_PASSES):
            if not self._queue:
                break
            batch, self._queue = self._queue, []
            self._depth += 1
            try:
                for ev in batch:
                    total += 1
                    for h in self._subs.get(ev.name, ()):
                        h(ev)
                    for h in self._subs.get("*", ()):
                        h(ev)
            finally:
                self._depth -= 1
            if self._next:
                self._queue.extend(self._next)
                self._next = []
        return total

    def clear(self):
        self._queue.clear()
        self._next.clear()
        self.log.clear()
