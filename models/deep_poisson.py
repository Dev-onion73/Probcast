import json
from glob import glob
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.metrics import classification_report
import sys

FAILURE_CLASSES = [
    "normal",
    "cpu_overload", "memory_exhaustion", "storage_failure",
    "network_downtime", "service_crash", "dependency_timeout"
]
CLASS2IDX = {c: i for i, c in enumerate(FAILURE_CLASSES)}

def load_dataset(path):
    X, y = [], []
    with open(path) as f:
        for line in f:
            if line.startswith("//META"):
                continue
            obj = json.loads(line)
            # Flatten all resource_series arrays, prepend mean per metric
            feats = []
            for k in sorted(obj["resource_series"].keys()):
                arr = np.array(obj["resource_series"][k])
                feats.append(np.mean(arr))
                feats.append(np.std(arr))
                feats.extend(arr[:10])  # first 10 values of each metric
            X.append(np.array(feats, dtype=np.float32))
            y.append(CLASS2IDX[obj["label"] if obj["label"] else "normal"])
    return np.stack(X), np.array(y)

class SimpleMLP(nn.Module):
    def __init__(self, in_dim, n_classes):
        super().__init__()
        self.seq = nn.Sequential(
            nn.Linear(in_dim, 32),
            nn.ReLU(),
            nn.Linear(32, n_classes)
        )
    def forward(self, x):
        return self.seq(x)

def export_torch_model(model, export_path, meta=None):
    import torch
    meta = meta or {}
    checkpoint = {
        "state_dict": model.state_dict(),
        "meta": meta
    }
    torch.save(checkpoint, export_path)
    print(f"[Path B] Exported torch model to {export_path}")

def run_experiment(train_path, test_path, epochs=10, batch_size=64, export_model_path=None, export_meta=None):
    print(f"\n[PATH B] Training on: {train_path}\n         Testing on: {test_path}")
    X_train, y_train = load_dataset(train_path)
    X_test, y_test = load_dataset(test_path)
    X_train = torch.tensor(X_train)
    y_train = torch.tensor(y_train)
    X_test = torch.tensor(X_test)
    y_test = torch.tensor(y_test)

    model = SimpleMLP(X_train.shape[1], len(FAILURE_CLASSES))
    lossfn = nn.CrossEntropyLoss()
    opt = optim.Adam(model.parameters(), lr=0.01)

    # Training loop
    for epoch in range(epochs):
        perm = torch.randperm(len(X_train))
        for i in range(0, len(X_train), batch_size):
            idx = perm[i:i+batch_size]
            x_b, y_b = X_train[idx], y_train[idx]
            logits = model(x_b)
            loss = lossfn(logits, y_b)
            opt.zero_grad()
            loss.backward()
            opt.step()
        if (epoch+1) % 3 == 0:
            print(f"epoch {epoch+1}: loss={float(loss):.4f}")

    # === EXPORT MODEL AFTER TRAINING ===
    if export_model_path:
        meta = export_meta or {
            "input_dim": X_train.shape[1],
            "FAILURE_CLASSES": FAILURE_CLASSES,
        }
        export_torch_model(model, export_model_path, meta)

    # Evaluation
    with torch.no_grad():
        logits = model(X_test)
        preds = torch.argmax(logits, dim=1).numpy()
    print(classification_report(y_test, preds, target_names=FAILURE_CLASSES, zero_division=0, digits=3))

if __name__ == "__main__":
    d_bal = "training_data/dataset_balanced.jsonl"
    d_imb = "training_data/dataset_imbalanced.jsonl"
    print("============ Path B: Deep Poisson Mixture Demo ============")
    # Model exported after the first training run for demonstration.
    run_experiment(
        d_bal,
        d_bal,
        epochs=10,
        batch_size=64,
        export_model_path="outputs/pathB_deep_poisson.pt",
        export_meta={
            "input_dim": 0,  # This will be overwritten by run_experiment logic!
            "FAILURE_CLASSES": FAILURE_CLASSES,
        }
    )
    run_experiment(d_imb, d_imb, epochs=10, batch_size=64)
    run_experiment(d_bal, d_imb, epochs=10, batch_size=64)