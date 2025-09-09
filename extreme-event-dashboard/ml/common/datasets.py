from typing import Any, Iterable, Tuple

class WeatherDataset:
    def __init__(self, data: Iterable[Any]):
        self.data = list(data)

    def __len__(self) -> int:
        return len(self.data)

    def __iter__(self):
        return iter(self.data)
