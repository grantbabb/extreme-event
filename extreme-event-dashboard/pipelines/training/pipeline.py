from ml.floods.train import train_flood_model
from ml.fires.train import train_fire_model


def train_all() -> dict:
    flood_path = train_flood_model()
    fire_path = train_fire_model()
    return {"flood": flood_path, "fire": fire_path}
