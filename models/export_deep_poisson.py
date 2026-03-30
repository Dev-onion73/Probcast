import torch

def export_torch_model(model, export_path, meta=None):
    """
    Save PyTorch model state_dict and any meta info (input shape, class names).
    """
    meta = meta or {}
    checkpoint = {
        "state_dict": model.state_dict(),
        "meta": meta
    }
    torch.save(checkpoint, export_path)
    print(f"Exported torch model to {export_path}")

def import_torch_model(model_class, in_dim, n_classes, export_path):
    """
    Load model state_dict and meta.
    Returns (model, meta-dict).
    """
    checkpoint = torch.load(export_path, map_location="cpu")
    model = model_class(in_dim, n_classes)
    model.load_state_dict(checkpoint["state_dict"])
    print(f"Imported torch model from {export_path}")
    return model, checkpoint.get("meta", {})

# Example usage: Place at end of deep_poisson.py after training

if __name__ == "__main__":
    # ... run training as normal ...
    # After training:
    meta = {
        "input_dim": X_train.shape[1],
        "FAILURE_CLASSES": FAILURE_CLASSES,
    }
    export_torch_model(model, "outputs/pathB_deep_poisson.pt", meta)
    # To load:
    # model, meta = import_torch_model(SimpleMLP, in_dim=meta["input_dim"], n_classes=len(meta["FAILURE_CLASSES"]), export_path="outputs/pathB_deep_poisson.pt")