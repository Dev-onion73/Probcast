class HierarchyGraph:
    """
    Simple dynamic hierarchy graph for L1 demo.
    """
    def __init__(self):
        self.nodes = {"host": [], "subnet": [], "environment": [], "org": []}
        self.tree = {
            "org": {
                "environments": {}
            }
        }

    def add_entity(self, meta):
        # meta: either dict or object with .host, .subnet, .environment, .org
        h = meta.get("host") if isinstance(meta, dict) else meta.host
        s = meta.get("subnet") if isinstance(meta, dict) else meta.subnet
        e = meta.get("environment") if isinstance(meta, dict) else meta.environment
        o = meta.get("org") if isinstance(meta, dict) else meta.org
        self.nodes["host"].append(h)
        self.nodes["subnet"].append(s)
        self.nodes["environment"].append(e)
        self.nodes["org"].append(o)
        envs = self.tree["org"]["environments"]
        if e not in envs:
            envs[e] = {}
        subnets = envs[e]
        if s not in subnets:
            subnets[s] = []
        if h not in subnets[s]:
            subnets[s].append(h)
    def build_from_entities(self, all_telemetry):
        for t in all_telemetry:
            self.add_entity(getattr(t, 'metadata', t))
        return self
    def as_tree(self):
        return self.tree