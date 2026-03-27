def make_labeled_event(entity_id, failure_class, window, resource_series,
                      journal_series, hierarchy, pool_context, label=None, confidence=1.0):
    return {
        "entity_id": entity_id,
        "failure_class": failure_class,
        "failure_timestamp": window[1] if failure_class else None,
        "window_start": window[0],
        "window_end": window[1],
        "hierarchy": hierarchy,
        "pool_context": pool_context,
        "resource_series": resource_series,
        "journal_series": journal_series,
        "label": label or failure_class,
        "confidence": confidence
    }