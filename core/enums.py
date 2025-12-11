from enum import Enum


class CommandType(Enum):
    MOVE_TO = 1
    PICK_UP = 2
    DROP_OBJECT = 3
    FOLLOW = 4
    REPAIR = 5
    RECHARGE = 6
    FORMATION = 7


class EditorMode(Enum):
    NONE, ADD_OBSTACLE, ADD_CHARGING_STATION, ADD_WORKSHOP = 0, 1, 2, 3
    ADD_OBJECT, DELETE = 4, 5
    ADD_OBJECT_SMALL, ADD_OBJECT_MEDIUM, ADD_OBJECT_LARGE = 6, 7, 8


class DroneState(Enum):
    IDLE, MOVING, EXECUTING, RECHARGING, REPAIRING, CARRYING = 1, 2, 3, 4, 5, 6

