from typing import List

class FireModel:
    def load(self, path: str) -> "FireModel":
        return self

    def save(self, path: str) -> None:
        pass

    def predict(self, features: List[float]) -> float:
        return 0.0
