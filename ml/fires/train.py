from ml.fires.model import FireModel
from ml.common.utils import set_seed


def train_fire_model(seed: int = 42) -> str:
    set_seed(seed)
    model = FireModel()
    # training logic placeholder
    model.save("/workspace/extreme-event-dashboard/data/processed/fire_model.bin")
    return "/workspace/extreme-event-dashboard/data/processed/fire_model.bin"
