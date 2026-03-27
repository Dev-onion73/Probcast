import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.metrics import classification_report, roc_auc_score
import pyro
import pyro.distributions as dist
from pyro.infer import SVI, Trace_ELBO, Predictive
from pyro.infer.autoguide import AutoDiagonalNormal
import json
import os

# === Settings ===
feature_metrics = [
    'cpu_usage', 'memory_usage', 'memory_cache', 'disk_io_read', 'disk_io_write',
    'network_rx', 'network_tx', 'request_rate', 'latency'
]
FAILURE_CLASSES = [
    'cpu_overload', 'memory_exhaustion', 'storage_failure',
    'network_downtime', 'service_crash', 'dependency_timeout', 'normal'
]
CLASS_TO_INDEX = {cls: i for i, cls in enumerate(FAILURE_CLASSES)}
NUM_METRIC_SAMPLES = 60

# === Data Loading ===
def load_probcast_jsonl_features(file_path):
    X = []
    y = []
    with open(file_path, 'r') as f:
        for line in f:
            obj = json.loads(line)
            features = []
            for metric in feature_metrics:
                vals = obj["resource_series"].get(metric, [0.] * NUM_METRIC_SAMPLES)
                vals = list(vals)[:NUM_METRIC_SAMPLES]
                if len(vals) < NUM_METRIC_SAMPLES:
                    vals += [0.] * (NUM_METRIC_SAMPLES - len(vals))
                features.extend(vals)
            label_str = obj.get("label") or obj.get("failure_class") or "normal"
            y.append(CLASS_TO_INDEX[str(label_str)])
            X.append(features)
    X = np.array(X)
    y = np.array(y)
    return X, y

file_path = "data/synthetic_labeled_events.jsonl"
if not os.path.exists(file_path):
    raise FileNotFoundError(f"{file_path} not found!")
X, y = load_probcast_jsonl_features(file_path)
print(f"Loaded dataset: X shape {X.shape}, y shape {y.shape}. Classes: {sorted(set(y))}")

X_tensor = torch.tensor(X, dtype=torch.float)
y_tensor = torch.tensor(y, dtype=torch.long)
N_CLASSES = len(FAILURE_CLASSES)
N_FEATS = X.shape[1]

# === Compute Class Weights ===
counts = np.bincount(y)
class_weights_np = 1.0 / (counts + 1e-6)
class_weights_np = class_weights_np / np.mean(class_weights_np)
class_weights = torch.tensor(class_weights_np, dtype=torch.float)
print("Class weights:", class_weights)

# === Pyro Model (with Class Imbalance Handling) ===
def make_pyro_model(N_CLASSES, N_FEATS, class_weights=None):
    def model(X, y=None):
        weights = pyro.sample('weights', dist.Normal(0, 1).expand([N_CLASSES, N_FEATS]).to_event(2))
        bias = pyro.sample('bias', dist.Normal(0, 1).expand([N_CLASSES]).to_event(1))
        logits = (X @ weights.T) + bias  # (N, K)
        with pyro.plate('data', X.shape[0]):
            obs_dist = dist.Categorical(logits=logits)
            if class_weights is not None and y is not None:
                # Pyro does not support per-sample Categorical weights, so use pyro.factor
                for i in range(X.shape[0]):
                    weight = class_weights[y[i]]
                    # (Log space, so higher weights increase that sample's influence)
                    pyro.factor(f"class_weight_{i}", torch.log(weight))
            pyro.sample('obs', obs_dist, obs=y)
    return model

pyro.clear_param_store()
model_a = make_pyro_model(N_CLASSES, N_FEATS, class_weights=class_weights)
guide_a = AutoDiagonalNormal(model_a)
svi = SVI(model_a, guide_a, pyro.optim.Adam({"lr": 0.01}), loss=Trace_ELBO())

print("Training Pyro model (Path A, Bayesian LR, class-weighted)...")
for step in range(150):
    loss = svi.step(X_tensor, y_tensor)
    if step % 25 == 0:
        print(f"    Iter {step:3d} | SVI loss {loss:.2f}")
print(f"Final Pyro SVI loss: {loss:.3f}")

# Predictive (handles both singleton and >1 MC case)
predictive_a = Predictive(model_a, guide=guide_a, num_samples=50)
with torch.no_grad():
    post_a = predictive_a(X_tensor)
    weights_samples = post_a["weights"]
    bias_samples = post_a["bias"]
    weights_mean = weights_samples.mean(axis=0).squeeze()
    bias_mean = bias_samples.mean(axis=0).squeeze()
    assert weights_mean.shape == (N_CLASSES, N_FEATS), f"Weights: {weights_mean.shape}"
    assert bias_mean.shape == (N_CLASSES,), f"Bias: {bias_mean.shape}"
    logits_a = (X_tensor @ torch.tensor(weights_mean, dtype=torch.float).T) + torch.tensor(bias_mean, dtype=torch.float)
    probs_a = F.softmax(logits_a, dim=1).cpu().numpy()

# === Deep Neural Classifier (class-weighted) ===
class DeepClassifier(nn.Module):
    def __init__(self, in_dim, n_classes, hidden_dim=96):
        super().__init__()
        self.fc1 = nn.Linear(in_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, n_classes)
    def forward(self, x):
        h = torch.relu(self.fc1(x))
        return self.fc2(h)

model_b = DeepClassifier(N_FEATS, N_CLASSES)
optimizer_b = torch.optim.Adam(model_b.parameters(), lr=0.003)
criterion = nn.CrossEntropyLoss(weight=class_weights)

BATCH_SIZE = 64
print("Training Deep NN classifier (Path B, class-weighted)...")
for epoch in range(50):
    model_b.train()
    idx = np.random.permutation(len(X_tensor))
    for start in range(0, len(X_tensor), BATCH_SIZE):
        batch = idx[start:start+BATCH_SIZE]
        logits = model_b(X_tensor[batch])
        loss = criterion(logits, y_tensor[batch])
        optimizer_b.zero_grad()
        loss.backward()
        optimizer_b.step()
    if epoch % 10 == 0:
        print(f"    Epoch {epoch:2d} | NN Loss: {loss.item():.4f}")

model_b.eval()
with torch.no_grad():
    logits_b = model_b(X_tensor)
    probs_b = F.softmax(logits_b, dim=1).cpu().numpy()

# === Fusion: Product of Experts ===
def product_of_experts_fusion(probs_a, probs_b, eps=1e-9):
    pa = np.clip(probs_a, eps, 1)
    pb = np.clip(probs_b, eps, 1)
    prod = pa * pb
    sum_prod = prod.sum(axis=1, keepdims=True)
    return prod / sum_prod

probs_fused = product_of_experts_fusion(probs_a, probs_b)
y_pred_fused = probs_fused.argmax(axis=1)

# === Evaluation/Reporting ===
print("\n--- Path A (Pyro, with class weights) ---")
print(classification_report(y, probs_a.argmax(axis=1), target_names=FAILURE_CLASSES))
print("--- Path B (NN, with class weights) ---")
print(classification_report(y, probs_b.argmax(axis=1), target_names=FAILURE_CLASSES))
print("--- L6 Fused ---")
print(classification_report(y, y_pred_fused, target_names=FAILURE_CLASSES))

try:
    rocauc = roc_auc_score(y, probs_fused, multi_class='ovr')
    print(f"Fused Path ROC-AUC (ovr): {rocauc:.3f}")
except Exception as e:
    print("ROC-AUC error:", e)

print("\nSample prediction outputs (first 5):")
for i in range(min(5, len(y))):
    print(f"Sample {i}:")
    print("  Pyro P : ", {FAILURE_CLASSES[j]: round(float(probs_a[i, j]), 3) for j in range(N_CLASSES)})
    print("  NN   P : ", {FAILURE_CLASSES[j]: round(float(probs_b[i, j]), 3) for j in range(N_CLASSES)})
    print("  Fused  : ", {FAILURE_CLASSES[j]: round(float(probs_fused[i, j]), 3) for j in range(N_CLASSES)})
    print("  True label:", FAILURE_CLASSES[y[i]], "; Fused pred:", FAILURE_CLASSES[y_pred_fused[i]])