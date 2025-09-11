from typing import List

class FloodModel:
    def load(self, path: str) -> "FloodModel":
        return self

    def save(self, path: str) -> None:
        pass

    def predict(self, features: List[float]) -> float:
        return 0.0
