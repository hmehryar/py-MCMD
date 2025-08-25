class NamdEngine:
    def __init__(self, cfg):
        self.cfg = cfg
        self.namd_template = self.cfg.path_namd_template
        # ... use namd_template when generating the per-cycle NAMD input ...

    def run(self):
        # Implement the logic to run NAMD simulation using the template
        pass