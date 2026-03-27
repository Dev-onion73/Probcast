def rolling_windows(series_len, window_size, step):
    """Yield (start, end) indices for rolling windows."""
    for start in range(0, series_len - window_size + 1, step):
        yield (start, start + window_size)