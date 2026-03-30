import json
import numpy as np
import torch
import pyro
import pyro.distributions as dist
from pyro.infer import SVI, Trace_ELBO, Predictive
from pyro.infer.autoguide import AutoNormal
from sklearn.metrics import classification_report

pyro.set_rng_seed(123)

FAILURE_CLASSES = [
    "normal",
    "cpu_overload", "memory_exhaustion", "storage_failure",
    "network_downtime", "service_crash", "dependency_timeout"
]
CLASS2IDX = {c: i for i, c in enumerate(FAILURE_CLASSES)}

def load_dataset(path):
    features, labels, hosts, subnets = [], [], [], []
    with open(path) as f:
        for line in f:
            if line.startswith("//META"):
                continue
            d = json.loads(line)
            feats = [np.mean(d["resource_series"][k]) for k in sorted(d["resource_series"].keys())]
            features.append(feats)
            label = d["label"] if d["label"] else "normal"
            labels.append(CLASS2IDX[label])
            hosts.append(d.get("hierarchy", {}).get("host", "unknown"))
            subnets.append(d.get("hierarchy", {}).get("subnet", "unknown"))
    features = np.array(features, dtype=np.float32)
    labels = np.array(labels)
    hosts = np.array(hosts)
    subnets = np.array(subnets)
    return features, labels, hosts, subnets

def make_hierarchy(hosts, subnets):
    hosts_list = sorted(set(hosts))
    subnets_list = sorted(set(subnets))
    host_map = {h:i for i,h in enumerate(hosts_list)}
    subnet_map = {s:i for i,s in enumerate(subnets_list)}
    # For datapoints
    entity_idx = np.array([host_map[h] for h in hosts])
    group_idx_per_entity = np.array([subnet_map[subnets[np.where(hosts==h)[0][0]]] for h in hosts_list])
    group_idx = np.array([subnet_map[s] for s in subnets])
    return entity_idx, group_idx, group_idx_per_entity, hosts_list, subnets_list

def hierarchical_poisson_model(X, y, entity_idx, group_idx_per_entity, num_entities, num_groups, num_classes):
    # entity_idx: (N,) each sample's entity index (row idx into entity params)
    # group_idx_per_entity: (num_entities,) for each entity, its group idx
    n = X.shape[0]
    for c in range(num_classes):
        mu_g = pyro.sample(f"mu_g_{c}", dist.Normal(0, 3).expand([num_groups]).to_event(1))
        sigma_g = pyro.sample(f"sigma_g_{c}", dist.HalfCauchy(1.0).expand([num_groups]).to_event(1))
        # Each entity (host) gets its own alpha from its subnet group
        with pyro.plate(f"entities_{c}", num_entities):
            alpha = pyro.sample(f"alpha_{c}", dist.Normal(mu_g[group_idx_per_entity], sigma_g[group_idx_per_entity]))
        beta = pyro.sample(f"beta_{c}", dist.Normal(0, 1))
        with pyro.plate(f"data_{c}", n):
            idx = entity_idx
            # Use mean for this class as feature; fallback to zero if missing col
            mean_feat = X[:, c] if c < X.shape[1] else torch.zeros(n)
            rate = torch.exp(alpha[idx] + beta + mean_feat)
            obs = (y == c).float()
            pyro.sample(f"y_{c}_obs", dist.Binomial(total_count=1, probs=rate/(1+rate)), obs=obs)

def export_pyro_model(guide, export_path, meta=None):
    import torch
    import pyro
    meta = meta or {}
    checkpoint = {
        "params": pyro.get_param_store().get_state(),
        "meta": meta
    }
    torch.save(checkpoint, export_path)
    print(f"[Path A] Exported Pyro model to {export_path}")

def run_experiment(train_path, test_path, steps=1000, export_model_path=None, export_meta=None):
    print(f"\n[PATH A-PYRO] Training on: {train_path}\n         Testing on: {test_path}")
    X_train, y_train, hosts_train, subnets_train = load_dataset(train_path)
    X_test, y_test, hosts_test, subnets_test = load_dataset(test_path)
    # Build hierarchy for training
    entity_idx_tr, group_idx_tr, group_idx_per_entity_tr, hosts_list, subnets_list = make_hierarchy(hosts_train, subnets_train)
    # For test: need indices into TRAIN entities and groups; mask OOV
    host_map = {h:i for i,h in enumerate(hosts_list)}
    subnet_map = {s:i for i,s in enumerate(subnets_list)}
    entity_idx_te = np.array([host_map[h] if h in host_map else -1 for h in hosts_test])
    group_idx_te = np.array([subnet_map[s] if s in subnet_map else -1 for s in subnets_test])
    valid_mask = (entity_idx_te >= 0)
    X_test, y_test, entity_idx_te = X_test[valid_mask], y_test[valid_mask], entity_idx_te[valid_mask]
    # Convert all to torch tensors
    X_train = torch.tensor(X_train)
    y_train = torch.tensor(y_train)
    entity_idx_tr = torch.tensor(entity_idx_tr, dtype=torch.long)
    group_idx_per_entity_tr = torch.tensor(group_idx_per_entity_tr, dtype=torch.long)
    num_entities = len(hosts_list)
    num_groups = len(subnets_list)
    num_classes = len(FAILURE_CLASSES)

    pyro.clear_param_store()
    guide = AutoNormal(hierarchical_poisson_model)
    svi = SVI(
        hierarchical_poisson_model,
        guide,
        pyro.optim.Adam({"lr": 0.04}),
        loss=Trace_ELBO()
    )
    # Training loop
    for step in range(steps):
        loss = svi.step(X_train, y_train, entity_idx_tr, group_idx_per_entity_tr, num_entities, num_groups, num_classes)
        if (step+1) % 250 == 0:
            print(f"step {step+1}: loss={loss:.1f}")

    # === EXPORT MODEL AFTER TRAINING ===
    if export_model_path:
        meta = export_meta or {
            "FAILURE_CLASSES": FAILURE_CLASSES,
            "hosts_list": hosts_list,
            "subnets_list": subnets_list,
        }
        export_pyro_model(guide, export_model_path, meta)

    # Inference
    X_test_ = torch.tensor(X_test)
    entity_idx_te = torch.tensor(entity_idx_te, dtype=torch.long)
    # Use group_idx_per_entity_tr (from train) for test too
    predictive = Predictive(hierarchical_poisson_model, guide=guide, num_samples=20)
    dummy_y = torch.full((len(X_test_),), -1)  # Not used
    result = predictive(X_test_, dummy_y, entity_idx_te, group_idx_per_entity_tr, num_entities, num_groups, num_classes)
    # For each class, get mean predicted rate per sample, build prob matrix
    pred_probs = []
    for c in range(num_classes):
        alpha = result[f"alpha_{c}"].mean(0).numpy()  # shape: [num_entities]
        beta = result[f"beta_{c}"].mean().item()
        mean_feat = X_test_[:, c] if c < X_test_.shape[1] else torch.zeros(len(X_test_))
        rate = np.exp(alpha[entity_idx_te] + beta + mean_feat.numpy())
        prob = rate / (1 + rate)
        pred_probs.append(prob)
    prob_mat = np.stack(pred_probs, axis=0).T  # shape [n_samples, n_classes]
    preds = np.argmax(prob_mat, axis=1)
    print(classification_report(y_test, preds, target_names=FAILURE_CLASSES, zero_division=0, digits=3))

if __name__ == "__main__":
    d_bal = "training_data/dataset_balanced.jsonl"
    d_imb = "training_data/dataset_imbalanced.jsonl"
    print("============ Path A: Hierarchical Bayesian Pyro Demo ============")
    # Model exported after the first training run for demonstration.
    run_experiment(
        d_bal,
        d_bal,
        steps=1000,
        export_model_path="outputs/pathA_hierarchical_pyro.pt",
        
    )
    run_experiment(d_imb, d_imb, steps=1000)
    run_experiment(d_bal, d_imb, steps=1000)