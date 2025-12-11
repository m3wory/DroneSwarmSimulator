from dataclasses import dataclass
from typing import Optional, Tuple

from core.enums import CommandType


@dataclass
class Command:
    cmd_type: CommandType
    target_pos: Optional[Tuple[float, float]] = None
    target_object: Optional[object] = None
    priority: int = 5
    radius: float = 100.0
    group_size: Optional[int] = None

