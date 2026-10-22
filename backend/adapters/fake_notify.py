"""A notifier for tests: remembers what it was asked to send."""

from adapters.notify import Notification


class FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[Notification] = []
        self.failing = False  # True: act like Discord is down

    def send(self, notification: Notification) -> bool:
        if self.failing:
            return False
        self.sent.append(notification)
        return True


class ExplodingNotifier:
    """Raises instead of returning False, to prove callers survive a misbehaving adapter."""

    def send(self, notification: Notification) -> bool:
        raise RuntimeError("boom")
