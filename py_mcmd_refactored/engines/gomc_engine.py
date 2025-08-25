class GomcEngine:
    def __init__(self, cfg):
        self.cfg = cfg
        self.gomc_template = self.cfg.path_gomc_template
        # ... use gomc_template when generating the per-cycle GOMC input ...
    def run(self):
        # Implement the logic to run GOMC simulation using the template
        pass