from staketaxcsv.orai.config_orai import localconfig
from staketaxcsv.common.progress import Progress

SECONDS_PER_PAGE = 4

class ProgressOrai(Progress):

    def __init__(self):
        super().__init__(localconfig)

    def set_estimate(self, count_pages):
        self.add_stage("default", count_pages, SECONDS_PER_PAGE)