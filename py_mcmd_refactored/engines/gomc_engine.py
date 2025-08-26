import logging
from engines.base import Engine as BaseEngine
logger = logging.getLogger(__name__)
class GomcEngine(BaseEngine):
    def __init__(self, cfg, engine_type="GOMC"):
        super().__init__(cfg, engine_type)
        # ... use gomc_template when generating the per-cycle GOMC input ...
    def run(self):
        # Implement the logic to run GOMC simulation using the template
        pass