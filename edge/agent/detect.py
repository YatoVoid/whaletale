from __future__ import annotations

import numpy as np
import numpy.typing as npt

BBoxNorm = tuple[float, float, float, float]
Frame = npt.NDArray[np.uint8]


class PersonDetector:
    """RT-DETR person detector (spec 6.1, Apache-2.0).

    Returns normalized (x1, y1, x2, y2) boxes so the rest of the pipeline is
    resolution-independent (spec rule 5.2.4).
    """

    def __init__(
        self,
        model_id: str = "PekingU/rtdetr_r50vd",
        device: str = "cpu",
        hf_cache: str = ".hf_cache",
        score_threshold: float = 0.5,
    ) -> None:
        import torch
        from transformers import AutoImageProcessor, AutoModelForObjectDetection

        self._torch = torch
        self.device = device if (device != "cuda" or torch.cuda.is_available()) else "cpu"
        self.score_threshold = score_threshold
        self.processor = AutoImageProcessor.from_pretrained(model_id, cache_dir=hf_cache)
        model = AutoModelForObjectDetection.from_pretrained(model_id, cache_dir=hf_cache)
        self.model = model.to(self.device).eval()

        id2label = self.model.config.id2label
        self._person_labels = {
            int(i) for i, label in id2label.items() if str(label).lower() == "person"
        }
        if not self._person_labels:
            raise RuntimeError(f"model {model_id!r} has no 'person' class in id2label")

    def detect(self, rgb: Frame) -> list[tuple[BBoxNorm, float]]:
        from PIL import Image

        h, w = rgb.shape[:2]
        inputs = self.processor(images=Image.fromarray(rgb), return_tensors="pt").to(self.device)
        with self._torch.no_grad():
            outputs = self.model(**inputs)
        result = self.processor.post_process_object_detection(
            outputs, target_sizes=[(h, w)], threshold=self.score_threshold
        )[0]

        dets: list[tuple[BBoxNorm, float]] = []
        for score, label, box in zip(
            result["scores"], result["labels"], result["boxes"], strict=True
        ):
            if int(label) not in self._person_labels:
                continue
            x1, y1, x2, y2 = (float(v) for v in box)
            dets.append(((x1 / w, y1 / h, x2 / w, y2 / h), float(score)))
        return dets
