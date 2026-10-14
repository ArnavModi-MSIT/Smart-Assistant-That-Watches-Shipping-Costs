from dataclasses import dataclass
from datetime import date
import math


@dataclass(frozen=True)
class Shipment:
    shipment_id: str
    origin: str
    destination: str
    route_type: str
    quantity: float
    distance: float
    cost: float
    day: date

    @property
    def route(self):
        return f"{self.origin}-{self.destination}"


@dataclass(frozen=True)
class Note:
    note_id: str
    day: date
    applies_to: str
    text: str


@dataclass(frozen=True)
class Thresholds:
    history_percent: float = 15.0
    peer_percent: float = 20.0
    minimum_rise_percent: float = 5.0

    def __post_init__(self):
        values = (self.history_percent, self.peer_percent, self.minimum_rise_percent)
        if any(not math.isfinite(v) or v <= 0 for v in values):
            raise ValueError("Thresholds must be finite, positive percentages.")
        if self.minimum_rise_percent > self.history_percent:
            raise ValueError("Minimum rise must not exceed the history threshold.")

    def candidate(self, history_change, peer_change):
        if history_change is None:
            return False
        def at_least(value, threshold):
            # Inclusive decimal boundaries can differ by a few binary float units.
            return math.isfinite(value) and (value >= threshold or math.isclose(value, threshold, rel_tol=1e-12, abs_tol=1e-12))
        return at_least(history_change, self.history_percent) or (
            at_least(history_change, self.minimum_rise_percent)
            and peer_change is not None
            and at_least(peer_change, self.peer_percent)
        )
