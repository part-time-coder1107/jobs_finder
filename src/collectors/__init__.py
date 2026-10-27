from src.collectors.greenhouse import GreenhouseCollector
from src.collectors.lever import LeverCollector
from src.collectors.workday import WorkdayCollector

COLLECTOR_REGISTRY = {
    "greenhouse": GreenhouseCollector,
    "lever": LeverCollector,
    "workday": WorkdayCollector,
}

__all__ = [
    "GreenhouseCollector",
    "LeverCollector",
    "WorkdayCollector",
    "COLLECTOR_REGISTRY",
]
