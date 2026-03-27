import argparse
import random
import json
import numpy as np

from config import (
    ENTITY_VARIANTS, DEFAULT_METRICS, FAILURE_CLASS_PROBS, ENTITY_TEMPLATE
)
from extract_params import extract_stats
from synth_trends import fbm_series, inject_failure
from synth_logs import make_journal_series
from formatter import make_labeled_event

N_TIMESTEPS_PER_WINDOW = 60      # 1 hour @ 1-min samples
WINDOW_STEP = 30                 # rolling window: step = 30
ENTITY_NAMES = ["sim-entity-%02d" % i for i in range(4)]  # You can expand

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n_entities", type=int, default=4)
    parser.add_argument("--n_windows", type=int, default=200)
    parser.add_argument("--output", type=str, default="../data/synthetic_labeled.jsonl")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--variant", choices=list(ENTITY_VARIANTS.keys()), default="etcd-minikube")
    parser.add_argument("--real_csv", type=str, default="../Seed_dataset/Real-FinalDataSet-Sheet1.csv")
    parser.add_argument("--attack_csv", type=str, default="../Seed_dataset/Attack-FinalDataSet-Sheet1.csv")
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    random.seed(args.seed)

    normal_stats = extract_stats(args.real_csv, ENTITY_VARIANTS[args.variant])
    attack_stats = extract_stats(args.attack_csv, ENTITY_VARIANTS[args.variant])

    with open(args.output, "w") as f:
        for n in range(args.n_entities):
            entity_id = ENTITY_NAMES[n % len(ENTITY_NAMES)]
            hierarchy = ENTITY_TEMPLATE.copy()
            hierarchy["host"] = entity_id
            pool_context = {}  # Can add group mean/stats if desired

            for w in range(args.n_windows):
                # Draw failure vs normal regime
                failure_class = random.choices(list(FAILURE_CLASS_PROBS.keys()), weights=FAILURE_CLASS_PROBS.values())[0]
                window_start_s = w * WINDOW_STEP
                window_end_s = window_start_s + N_TIMESTEPS_PER_WINDOW * 60

                resource_series = {}
                for metric in DEFAULT_METRICS:
                    mean = normal_stats[metric]["mean"]
                    std = normal_stats[metric]["std"]
                    base = fbm_series(N_TIMESTEPS_PER_WINDOW, mean=mean, std=std, seed=args.seed + n + w)
                    a_mean = attack_stats[metric]["mean"]
                    if failure_class:

                        if failure_class == "cpu_overload":
                            series = inject_failure(
                                base, attack_mean=a_mean, slope=(a_mean - mean) / N_TIMESTEPS_PER_WINDOW,             burst_scale=std * 2,
                                burst_freq=0.15, grad_start=int(N_TIMESTEPS_PER_WINDOW * 0.7), seed=args.seed + n + w
                            )
                        elif failure_class == "memory_exhaustion":
        # memory_usage: slow climb with occasional plateaus, high at end
                            series = inject_failure(
                                base, attack_mean=a_mean, slope=(a_mean - mean) / (N_TIMESTEPS_PER_WINDOW * 0.8), burst_scale=std * 1.5,
                                burst_freq=0.1, grad_start=int(N_TIMESTEPS_PER_WINDOW * 0.5), seed=args.seed + n + w
                            )
                        elif failure_class == "storage_failure":
        # disk_io_read spike, write collapse (simulate with shape)
                            if metric == "disk_io_write":
            # write collapse
                                series = base - np.linspace(0, base.max(), N_TIMESTEPS_PER_WINDOW)
                            elif metric == "disk_io_read":
            # read spike        
                                series = base + np.linspace(0, a_mean * 2, N_TIMESTEPS_PER_WINDOW)
                            else:
                                series = base
                        elif failure_class == "network_downtime":
        # Rx/Tx collapse together
                            if metric in ("network_rx", "network_tx"):
                                series = np.linspace(mean, a_mean * 0.1, N_TIMESTEPS_PER_WINDOW)
                            else:
                                series = base
                        elif failure_class == "service_crash":
        # abrupt step down at ~window_end
                            cut = int(N_TIMESTEPS_PER_WINDOW * 0.8)
                            series = base.copy()
                            series[cut:] = mean * 0.1
                        elif failure_class == "dependency_timeout":
        # plausible: add a late spike in app/request latency metric if available
                            series = base
                        else:
                            series = base
                    else:
                        series = base
                      
                    resource_series[metric] = [float("{:.4f}".format(v)) for v in series]

                journal_series = make_journal_series(
                    failure_class, window_start_s, window_end_s
                )

                levent = make_labeled_event(
                    entity_id, failure_class, [window_start_s, window_end_s],
                    resource_series, journal_series,
                    hierarchy, pool_context, label=failure_class, confidence=1.0
                )
                f.write(json.dumps(levent) + "\n")

if __name__ == "__main__":
    main()