from enum import Enum

class CommandType(Enum):
    MOVE_TO = 1
    PICK_UP = 2
    DROP_OBJECT = 3
    FOLLOW = 4
    REPAIR = 5
    RECHARGE = 6
    FORMATION = 7

class DroneState(Enum):
    IDLE, MOVING, EXECUTING, RECHARGING, REPAIRING, CARRYING = 1, 2, 3, 4, 5, 6