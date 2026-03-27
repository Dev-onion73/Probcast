import pandas as pd

def extract_stats(seed_csv, metric_map):
    """Extracts mean and std for each metric given the csv file and column mapping."""
    df = pd.read_csv(seed_csv)
    stats = {}
    for canonical_key, csv_col in metric_map.items():
        stats[canonical_key] = {
            'mean': df[csv_col].mean(),
            'std':  df[csv_col].std()
        }
    return stats