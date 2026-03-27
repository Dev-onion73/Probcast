import numpy as np

def fbm_series(length, mean=0, std=1, hurst=0.7, seed=None):
    rng = np.random.default_rng(seed)
    steps = rng.normal(0, std, size=length)
    s = np.cumsum(steps)
    # Normalize to mean/std
    s = (s - np.mean(s)) / (np.std(s) + 1e-6)
    s = s * std + mean
    return s

def inject_failure(series, attack_mean, slope=0.006, burst_scale=0.02, burst_freq=0.08, grad_start=None, seed=None):
    rng = np.random.default_rng(seed)
    s = series.copy()
    n = len(s)
    if grad_start is None:
        grad_start = int(n * 0.5)
    # Gradually increase to attack_mean
    for i in range(grad_start, n):
        s[i] += (i - grad_start + 1) * slope
        if rng.random() < burst_freq:
            s[i] += rng.normal(0, burst_scale)
    # Clip to ensure not overshooting
    s[grad_start:] = np.clip(s[grad_start:], None, attack_mean)
    return s