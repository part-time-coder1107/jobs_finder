from abc import ABC, abstractmethod
from typing import List, Dict, Any
from src.models import RawJob


class BaseCollector(ABC):
    """
    Abstract base class for all ATS & job board collectors.
    Separates job collection from filtering/ranking.
    """

    platform_name: str = "base"

    @abstractmethod
    def collect(
        self,
        roles: List[str],
        locations: List[str],
        config: Dict[str, Any],
    ) -> List[RawJob]:
        pass
