from ml.floods.model import FloodModel
from ml.common.utils import set_seed


def train_flood_model(seed: int = 42) -> str:
    set_seed(seed)
    model = FloodModel()
    # training logic placeholder
    model.save("/workspace/extreme-event-dashboard/data/processed/flood_model.bin")
    return "/workspace/extreme-event-dashboard/data/processed/flood_model.bin"
