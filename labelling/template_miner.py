from typing import List, Dict
import re

def extract_templates(journal_records: List[dict]) -> Dict[str, List[str]]:
    """
    Groups journal log messages into crude templates.
    Replace numbers, PIDs, and hostnames with *
    """
    def template(msg):
        msg = re.sub(r'\d+', '<*>', msg)
        msg = re.sub(r'host-[\w-]+', '<*>', msg)
        return msg

    clusters = {}
    for rec in journal_records:
        t = template(rec['message'])
        clusters.setdefault(t, []).append(rec['message'])
    return clusters  # template_str → [examples]