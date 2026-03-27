"""
ProbCast L5: Deep Poisson Mixture Model (Path B) — FIXED VERSION

Bugs fixed vs Version5:
  1. CRITICAL — division by zero in Poisson PMF:
       Original: ws * exp(-lam) * lam^y / lgamma(y+1)
       lgamma(0+1) = lgamma(2) = log(Gamma(1)) = log(0!) = 0
       lgamma(1+1) = lgamma(2) = log(Gamma(2)) = log(1!) = 0
       → divides by 0 for EVERY sample (y is always 0 or 1)
       → PMF = inf everywhere → clamped to 1e-7 → loss stuck at ~16 → model never trains

       Fix: use numerically-stable log-domain formulation
         log P(y|lam) = y*log(lam) - lam - lgamma(y+1)   ← lgamma in the right place
         then logsumexp across components

  2. Risk score was expected rate E[Y]=Σ w_k λ_k (a Poisson rate, not a probability).
     Fix: risk = P(Y≥1) = 1 - P(Y=0) = 1 - Σ_k w_k * exp(-λ_k)
     This is a proper probability in [0,1] — correct for Brier score.

  3. PMF loop was hardcoded for exactly 2 components.
     Fix: generalise loss to work for any n_components.
"""

# ── 1. Setup ──────────────────────────────────────────────────────────────────
import torch
import torch.nn as nn
import pandas as pd
import numpy as np
import json
import matplotlib.pyplot as plt
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss

torch.manual_seed(1)


# ── 2. Load data ──────────────────────────────────────────────────────────────
def load_jsonl(filename):
    with open(filename) as f:
        return [json.loads(line) for line in f]

events = load_jsonl("../data/synthetics.jsonl")
df = pd.DataFrame(events)

print("Entities:", df['entity_id'].unique())
print("Classes: ", df['label'].unique())


# ── 3. Window feature extraction ─────────────────────────────────────────────
# Auto-detect metrics from the data
sample_series = df.iloc[0]['resource_series']
ALL_METRICS = sorted(sample_series.keys())
TARGET_CLASS = 'cpu_overload'    # binary: this class vs. all others

def extract_X_y(df, entity_id, label_class, metrics):
    dd = df[df.entity_id == entity_id]
    X = np.stack([
        np.concatenate([np.array(w[m]) for m in metrics])
        for w in dd['resource_series']
    ]).astype(np.float32)
    y = (dd['label'] == label_class).astype(float).values
    return X, y

entity_id = df.entity_id.unique()[0]
X, y = extract_X_y(df, entity_id, TARGET_CLASS, ALL_METRICS)
print(f"\nX shape : {X.shape}  |  positives (failures): {y.sum():.0f} / {len(y)}")


# ── 4. Deep Poisson Mixture definition ───────────────────────────────────────
class DeepPoissonMixture(nn.Module):
    """
    Shallow feedforward network that outputs K Poisson mixture weights + rates.
    y ~ Σ_k π_k(x) · Poisson(λ_k(x))
    """
    def __init__(self, in_features, n_components=3):
        super().__init__()
        self.n_components = n_components
        self.net = nn.Sequential(
            nn.Linear(in_features, 64),
            nn.ReLU(),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, n_components * 2),   # weights + rates
        )

    def forward(self, x):
        out  = self.net(x)
        ws   = torch.softmax(out[:, :self.n_components], dim=-1)   # [N, K]
        lams = torch.exp(out[:, self.n_components:]) + 1e-6        # [N, K] positive
        return ws, lams


# ── 5. Numerically-stable Poisson mixture NLL  (BUG 1 + 3 fixed) ─────────────
def mixture_poisson_nll(ws, lams, y):
    """
    Negative log-likelihood of a K-component Poisson mixture.

    log P(y | mixture) = log Σ_k w_k · Poisson(y; λ_k)
                       = logsumexp_k [ log w_k + y*log(λ_k) - λ_k - log(y!) ]

    BUG 1 FIX:  lgamma(y+1) is used as log(y!) INSIDE the log, not as a divisor.
                Original code divided by lgamma(y+1) which equals 0 for y∈{0,1}.
    BUG 3 FIX:  works for any K because we use matrix ops.
    """
    y_col    = y.unsqueeze(1)                                  # [N, 1]
    log_lam  = torch.log(lams + 1e-8)                         # [N, K]
    log_fact = torch.lgamma(y_col + 1)                        # [N, 1]  = log(y!)

    # log P(y | Poisson(λ_k))  for each k
    log_poisson = y_col * log_lam - lams - log_fact           # [N, K]

    # log mixture probability  (logsumexp for numerical stability)
    log_ws    = torch.log(ws + 1e-8)                          # [N, K]
    log_probs = log_ws + log_poisson                          # [N, K]
    log_mix   = torch.logsumexp(log_probs, dim=1)             # [N]

    return -log_mix.mean()


# ── 6. Training ───────────────────────────────────────────────────────────────
model     = DeepPoissonMixture(X.shape[1], n_components=3)
optimizer = torch.optim.Adam(model.parameters(), lr=5e-3)

X_tensor = torch.tensor(X, dtype=torch.float)
y_tensor = torch.tensor(y, dtype=torch.float)

losses = []
for epoch in range(150):
    model.train()
    ws, lams = model(X_tensor)
    loss = mixture_poisson_nll(ws, lams, y_tensor)
    optimizer.zero_grad()
    loss.backward()
    optimizer.step()
    losses.append(loss.item())
    if epoch % 30 == 0:
        print(f"epoch {epoch:3d}  NLL = {loss.item():.4f}")

plt.figure()
plt.plot(losses)
plt.title("Negative Log-Likelihood Loss")
plt.xlabel("Epoch")
plt.ylabel("NLL")
plt.tight_layout()
plt.savefig("l5_nll_loss.png", dpi=100)
plt.close()


# ── 7. Inference  (BUG 2 fixed) ───────────────────────────────────────────────
model.eval()
with torch.no_grad():
    ws, lams = model(X_tensor)

    # BUG 2 FIX: proper failure probability P(Y≥1) = 1 - P(Y=0)
    # P(Y=0 | Poisson mixture) = Σ_k w_k * exp(-λ_k)
    p_zero = (ws * torch.exp(-lams)).sum(dim=1)      # [N]
    risks  = (1.0 - p_zero).numpy()                  # proper probability in [0,1]

    # Expected Poisson rate (kept for reference, NOT used for evaluation)
    expected_rate = (ws * lams).sum(dim=1).numpy()   # [N]

print(f"\nRisk score range: [{risks.min():.4f}, {risks.max():.4f}]")
print(f"Mean risk (failure):  {risks[y == 1].mean():.4f}")
print(f"Mean risk (normal) :  {risks[y == 0].mean():.4f}")


# ── 8. Visualise ──────────────────────────────────────────────────────────────
plt.figure(figsize=(8, 3))
plt.hist(risks[y == 0], bins=30, alpha=0.7, label='normal', density=True)
plt.hist(risks[y == 1], bins=30, alpha=0.7, label=TARGET_CLASS, density=True)
plt.xlabel("P(failure) = 1 − P(Y=0)")
plt.ylabel("Density")
plt.legend()
plt.title(f"Predicted failure probability by class ({TARGET_CLASS})")
plt.tight_layout()
plt.savefig("l5_risk_distribution.png", dpi=100)
plt.close()


# ── 9. Evaluation ─────────────────────────────────────────────────────────────
roc   = roc_auc_score(y, risks)
prc   = average_precision_score(y, risks)
brier = brier_score_loss(y, risks)        # correct: risks are probabilities now

print(f"\nROC-AUC : {roc:.3f}")
print(f"PRC-AUC : {prc:.3f}")
print(f"Brier   : {brier:.3f}")

print("\nDone — l5_deep_poisson_mixture_fixed.py completed successfully.")
