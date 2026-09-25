import json
import re
import unicodedata
from pathlib import Path


class CertifiedMetricResolver:

    def __init__(self, registry_path):
        self.registry_path = Path(registry_path)
        with open(self.registry_path, "r", encoding="utf-8") as file:
            self.metrics = json.load(file).get("metrics", [])

    def _normalize(self, value):
        value = str(value or "").lower()
        value = "".join(
            char
            for char in unicodedata.normalize("NFD", value)
            if unicodedata.category(char) != "Mn"
        )
        value = re.sub(r"[^a-z0-9\s]", " ", value)
        return re.sub(r"\s+", " ", value).strip()

    def resolve(self, question):
        normalized_question = self._normalize(question)
        matches = []

        for metric in self.metrics:
            best_alias_score = 0

            for alias in metric.get("aliases", []):
                normalized_alias = self._normalize(alias)

                if (
                    normalized_alias
                    and normalized_alias in normalized_question
                ):
                    best_alias_score = max(
                        best_alias_score,
                        len(normalized_alias.split()),
                    )

            if best_alias_score > 0:
                candidate = metric.copy()
                candidate["match_score"] = best_alias_score
                matches.append(candidate)

        if not matches:
            return {"status": "not_found"}

        matches.sort(
            key=lambda item: item["match_score"],
            reverse=True,
        )

        best = matches[0]

        return {
            "status": "resolved",
            "metric_id": best.get("id"),
            "label": best.get("label"),
            "dashboard": best.get("dashboard"),
            "semantic_model": best.get("semantic_model"),
            "expression": best.get("expression"),
            "source": best.get("source"),
            "visual_title": best.get("visual_title"),
        }
