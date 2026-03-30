import json
from glob import glob
import numpy as np
from sklearn.linear_model import PoissonRegressor
from sklearn.metrics import classification_report
import sys

FAILURE_CLASSES = [
    "normal",
    "cpu_overload", "memory_exhaustion", "storage_failure",
    "network_downtime", "service_crash", "dependency_timeout"
]

def load_dataset(path):
    X, y = [], []
    with open(path) as f:
        for line in f:
            if line.startswith("//META"):
                continue
            obj = json.loads(line)
            # Features: simple mean of resource_series; label: failure class
            feats = [np.mean(obj["resource_series"][k]) for k in sorted(obj["resource_series"].keys())]
            X.append(feats)
            y.append(obj["label"] if obj["label"] else "normal")
    return np.array(X), np.array(y)

def run_experiment(train_path, test_path):
    print(f"\n[PATH A] Training on: {train_path}\n         Testing on: {test_path}")
    X_train, y_train = load_dataset(train_path)
    X_test, y_test = load_dataset(test_path)
    # PoissonRegressor can't do multiclass; we'll use one-vs-rest as a stand-in
    from sklearn.preprocessing import LabelBinarizer
    lb = LabelBinarizer()
    Y_train = lb.fit_transform(y_train)
    Y_test = lb.transform(y_test)
    # Fit one-vs-rest Poisson per class for illustration
    models = []
    for i, cls in enumerate(lb.classes_):
        model = PoissonRegressor(max_iter=500)
        model.fit(X_train, Y_train[:, i])
        models.append(model)
    # Predict: pick class with the largest predicted Poisson mean
    preds = []
    for x in X_test:
        rates = [float(m.predict([x])[0]) for m in models]
        pred_idx = int(np.argmax(rates))
        preds.append(lb.classes_[pred_idx])
    print(classification_report(y_test, preds, zero_division=0, digits=3))

if __name__ == "__main__":
    d_bal = "training_data/dataset_balanced.jsonl"
    d_imb = "training_data/dataset_imbalanced.jsonl"
    print("============ Path A: Hierarchical Poisson Demo ============")
    # Balanced
    run_experiment(d_bal, d_bal)
    # Imbalanced
    run_experiment(d_imb, d_imb)
    # Balanced → Imbalanced
    run_experiment(d_bal, d_imb)