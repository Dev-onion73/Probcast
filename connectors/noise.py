import numpy as np

def fbm_sample(t: float, hurst: float = 0.7, scale: float = 0.04, seed=None) -> float:
    rnd = np.random.RandomState(seed)
    # crude, tiny simulation: for actual fBm use a lib, but here just a sum of sines
    base = np.sin(t/60) + 0.1*np.sin(t/360)
    trend = hurst * np.sin(t/720)
    noise = rnd.normal(0, scale)
    return base + trend + noise

def perlin_noise(t: float, scale: float = 1.0, seed=None) -> float:
    rnd = np.random.RandomState(seed)
    # simple noisy cosine for demo
    return np.cos(t/300) * scale + rnd.normal(0, scale/5)