"""Model-independent, causal deadline monitoring for one response target."""

import math


def _milliseconds(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("Times must be finite nonnegative milliseconds.")
    return value


class ResponseTimeout:
    """Freeze a prediction at send time; emit once on the observed clock.

    Create separate instances for ACK and contact. The caller supplies current
    completion/censoring events, never future outcomes. A late terminal event
    preserves the timeout. Event routing and calibration are separate concerns.
    """

    def __init__(self, *, sent_ms, predicted_ms, margin_ms):
        self._last_ms = _milliseconds(sent_ms)
        self._deadline_ms = _milliseconds(
            sent_ms + _milliseconds(predicted_ms) + _milliseconds(margin_ms)
        )
        self._alarm_ms = None
        self._closed = False

    @property
    def deadline_ms(self):
        return self._deadline_ms

    @property
    def alarm_ms(self):
        """First observed timeout time, retained after completion/censoring."""
        return self._alarm_ms

    @property
    def closed(self):
        return self._closed

    def advance(self, now_ms, *, completed=False, censored=False):
        """Return True only for a new timeout at this observation.

        Resolve all events at now_ms before calling. Censoring includes loss of
        observability or a competing accepted target; it is not a fault label.
        """
        now_ms = _milliseconds(now_ms)
        if now_ms < self._last_ms:
            raise ValueError("The observed clock must not move backwards.")
        if type(completed) is not bool or type(censored) is not bool:
            raise ValueError("Terminal event flags must be boolean.")
        if completed and censored:
            raise ValueError("A response cannot be completed and censored together.")
        self._last_ms = now_ms
        if self._closed:
            return False
        new_alarm = self._alarm_ms is None and now_ms > self._deadline_ms
        if new_alarm:
            self._alarm_ms = now_ms
        self._closed = completed or censored
        return new_alarm
