from ml.floods.model import FloodModel
from ml.fires.model import FireModel
from typing import Dict, List


def load_models() -> Dict[str, object]:
    flood = FloodModel().load("/workspace/extreme-event-dashboard/data/processed/flood_model.bin")
    fire = FireModel().load("/workspace/extreme-event-dashboard/data/processed/fire_model.bin")
    return {"flood": flood, "fire": fire}


def run_inference(models: Dict[str, object], features: List[float]) -> Dict[str, float]:
    return {
        "flood": models["flood"].predict(features),
        "fire": models["fire"].predict(features),
    }
