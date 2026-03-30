import torch
import pyro
from pyro.infer.autoguide import AutoNormal

def export_pyro_model(guide, export_path, meta=None):
    """
    Save Pyro guide parameters and any meta info (e.g. class names, hierarchy lists).
    """
    meta = meta or {}
    checkpoint = {
        "params": pyro.get_param_store().get_state(),
        "meta": meta
    }
    torch.save(checkpoint, export_path)
    print(f"Exported Pyro model to {export_path}")

def import_pyro_model(model, export_path):
    """
    Load Pyro guide parameters and associated meta for inference.
    Returns (guide, meta-dict).
    """
    checkpoint = torch.load(export_path, map_location="cpu")
    guide = AutoNormal(model)
    pyro.get_param_store().set_state(checkpoint["params"])
    print(f"Imported Pyro model from {export_path}")
    return guide, checkpoint.get("meta", {})

# Example usage: Place at end of hierarchical_pyro.py after training

if __name__ == "__main__":
    # ... run training as normal ...
    # After training:
    meta = {
        "FAILURE_CLASSES": FAILURE_CLASSES,
        "hosts_list": hosts_list,
        "subnets_list": subnets_list,
    }
    export_pyro_model(guide, "outputs/pathA_hierarchical_pyro.pt", meta)
    # To load:
    # guide, meta = import_pyro_model(hierarchical_poisson_model, "outputs/pathA_hierarchical_pyro.pt")