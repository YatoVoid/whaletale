from __future__ import annotations

import norfair
import numpy as np


class GroundPointTracker:
    """Norfair tracker over normalized ground points (MIT, spec 6.1).

    We track the ground point directly rather than the full box: it's what zone
    containment needs, and it keeps the tracker's distance metric in one
    normalized space.
    """

    def __init__(self, distance_threshold: float = 0.06) -> None:
        self._tracker = norfair.Tracker(
            distance_function="euclidean",
            distance_threshold=distance_threshold,
            hit_counter_max=15,
            initialization_delay=2,
        )

    def update(self, ground_points: list[tuple[float, float]]) -> dict[int, tuple[float, float]]:
        detections = [norfair.Detection(points=np.array([[x, y]])) for x, y in ground_points]
        tracked = self._tracker.update(detections=detections)
        out: dict[int, tuple[float, float]] = {}
        for obj in tracked:
            if obj.id is None:
                continue
            est = obj.estimate[0]
            out[int(obj.id)] = (float(est[0]), float(est[1]))
        return out
