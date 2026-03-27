"""
ProbCast L4: Hierarchical Bayesian Poisson Model (Path A)  — FIXED VERSION

Bugs fixed vs Version5:
  1. feature_metrics inconsistency: diagnostics cell used 8 metrics (480 feature names)
     while extraction used 4 (240 columns) → ValueError when building DataFrame.
     Fix: auto-detect metrics from data; use the same list everywhere.
  2. y label mapping: None was inconsistently mapped vs 'normal'.
     Fix: normalise None → 'normal' in one place, consistently.
  3. y_pred never explicitly computed but used in diagnostics → silent NameError risk.
     Fix: add  y_pred = np.argmax(probs, axis=1)  right after probs is computed.
  4. Standalone evaluation cell: roc_auc_score(y, probs) missing multi_class='ovr';
     brier_score_loss(y, probs) called with multiclass probs → wrong shape.
     Fix: correct both calls; add per-class OVR brier scores.
"""

# ── 1. Setup ──────────────────────────────────────────────────────────────────
import torch
import pyro
import pyro.distributions as dist
from pyro.infer import SVI, Trace_ELBO, Predictive
from pyro.optim import Adam
import numpy as np
import pandas as pd
import json
import matplotlib.pyplot as plt
from sklearn.metrics import (
    roc_auc_score, average_precision_score, brier_score_loss,
    classification_report
)
from sklearn.preprocessing import label_binarize

pyro.set_rng_seed(0)


# ── 2. Load data ──────────────────────────────────────────────────────────────
def load_jsonl(filename):
    with open(filename) as f:
        return [json.loads(line) for line in f]

events = load_jsonl("../data/synthetics.jsonl")
df = pd.DataFrame(events)

print("Available entities:", df['entity_id'].unique())
print("Raw label values:  ", df['label'].unique())


# ── 3. Feature & label extraction  (BUG 1 + 2 fixed) ────────────────────────
FAILURE_CLASSES = [
    'cpu_overload',
    'memory_exhaustion',
    'storage_failure',
    'network_downtime',
    'service_crash',
    'dependency_timeout',
    'normal',       # ← 'normal' string; None labels are mapped here (fix #2)
]
CLASS_TO_INDEX = {cls: i for i, cls in enumerate(FAILURE_CLASSES)}
n_classes = len(FAILURE_CLASSES)

# BUG 1 FIX: auto-detect metrics from the actual data, use ONE list everywhere
sample_series = df.iloc[0]['resource_series']
feature_metrics = sorted(sample_series.keys())   # deterministic order
window_len = len(next(iter(sample_series.values())))
print(f"\nDetected metrics : {feature_metrics}")
print(f"Window length    : {window_len} timesteps")
print(f"Feature dim      : {len(feature_metrics) * window_len}")


def extract_X_y(df, entity_id, metrics):
    dd = df[df.entity_id == entity_id]
    X = np.stack([
        np.concatenate([np.array(w[m]) for m in metrics])
        for w in dd['resource_series']
    ])
    # BUG 2 FIX: normalise None → 'normal'
    y = np.array([
        CLASS_TO_INDEX.get(lbl if lbl is not None else 'normal',
                           CLASS_TO_INDEX['normal'])
        for lbl in dd['label']
    ])
    return X.astype(np.float32), y


entity_id = df.entity_id.unique()[0]
X, y = extract_X_y(df, entity_id, feature_metrics)
print(f"\nX shape : {X.shape}   y counts : {pd.Series(y).value_counts().to_dict()}")


# ── 4. Multiclass Bayesian model ─────────────────────────────────────────────
class MulticlassBayesModel:
    """
    Bayesian multinomial logistic regression.
    Priors: weights ~ N(0,1), bias ~ N(0,1).
    Likelihood: Categorical(softmax(X @ W.T + b)).
    """
    def __init__(self, in_features, n_classes):
        self.n_classes   = n_classes
        self.in_features = in_features
        self.guide = pyro.infer.autoguide.AutoNormal(self.model)

    def model(self, X, y=None):
        weights = pyro.sample(
            "weights",
            dist.Normal(0., 1.).expand([self.n_classes, self.in_features]).to_event(2)
        )
        bias = pyro.sample(
            "bias",
            dist.Normal(0., 1.).expand([self.n_classes]).to_event(1)
        )
        logits = X @ weights.t() + bias          # [N, n_classes]
        with pyro.plate("data", X.shape[0]):
            pyro.sample("obs", dist.Categorical(logits=logits), obs=y)


pyro.clear_param_store()
X_tensor = torch.tensor(X, dtype=torch.float)
y_tensor = torch.tensor(y, dtype=torch.long)

bayes = MulticlassBayesModel(X.shape[1], n_classes)
svi   = SVI(bayes.model, bayes.guide, Adam({"lr": 0.01}), Trace_ELBO())

losses = []
for step in range(750):
    loss = svi.step(X_tensor, y_tensor)
    losses.append(loss)

plt.figure()
plt.plot(losses)
plt.title("ELBO Loss (Multiclass)")
plt.xlabel("Step")
plt.ylabel("Loss")
plt.tight_layout()
plt.savefig("l4_elbo_loss.png", dpi=100)
plt.close()


# ── 5. Posterior predictive  (BUG 3 fixed) ───────────────────────────────────
with torch.no_grad():
    predictive = Predictive(bayes.model, guide=bayes.guide, num_samples=100)
    post = predictive(X_tensor)

    weights_mean = post["weights"].mean(0)
    bias_mean    = post["bias"].mean(0)

    if weights_mean.ndim > 2:
        weights_mean = weights_mean.squeeze(0)   # [n_classes, n_features]

    logits = X_tensor @ weights_mean.t() + bias_mean
    probs  = torch.softmax(logits, dim=1).numpy()  # [N, n_classes]

# BUG 3 FIX: compute y_pred explicitly right here
y_pred = np.argmax(probs, axis=1)


# ── 6. Evaluation  (BUG 4 fixed) ─────────────────────────────────────────────
print("\n── Classification report ──")
print(classification_report(y, y_pred, target_names=FAILURE_CLASSES,
                             zero_division=0))

print(f"Overall accuracy: {(y == y_pred).mean():.3f}")

# ROC AUC — needs multi_class='ovr' for multiclass (fix #4)
try:
    roc = roc_auc_score(y, probs, multi_class='ovr')
    print(f"Multiclass ROC-AUC (ovr): {roc:.3f}")
except Exception as e:
    print(f"ROC-AUC error: {e}")

# Brier score — per-class OVR, then averaged (fix #4)
# brier_score_loss requires binary labels; binarize for OVR
y_bin = label_binarize(y, classes=list(range(n_classes)))
brier_per_class = [
    brier_score_loss(y_bin[:, i], probs[:, i])
    for i in range(n_classes)
]
print(f"\nPer-class Brier scores (OVR):")
for cls, bs in zip(FAILURE_CLASSES, brier_per_class):
    print(f"  {cls:<22s}: {bs:.3f}")
print(f"Mean Brier (OVR): {np.mean(brier_per_class):.3f}")


# ── 7. Diagnostics ────────────────────────────────────────────────────────────
# BUG 1 FIX: feature_names uses the SAME feature_metrics as extraction
feature_names = [f"{m}_t{i}" for m in feature_metrics for i in range(window_len)]
assert len(feature_names) == X.shape[1], \
    f"feature_names ({len(feature_names)}) != X columns ({X.shape[1]})"

print(f"\nfeature_names count: {len(feature_names)}  (matches X columns: {X.shape[1]})")

# Per-class feature means
df_plot = pd.DataFrame(X, columns=feature_names)
df_plot["label"] = y
means = df_plot.groupby("label").mean()
means.index = [FAILURE_CLASSES[i] for i in means.index]
print("\n── Per-class mean of last timestep per metric ──")
last_ts_cols = [f"{m}_t{window_len-1}" for m in feature_metrics]
print(means[last_ts_cols].to_string())

print("\nDone — l4_hierarchical_bayes_fixed.py completed successfully.")
