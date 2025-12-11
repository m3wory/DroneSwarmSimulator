import pygame

import config
from enum import Enum
from core.enums import DroneState
from core.vector import Vector2D


class CargoType(Enum):
    SMALL = 1
    MEDIUM = 2
    LARGE = 3


class GameObject:
    def __init__(self, x: float, y: float, cargo_type: CargoType = CargoType.SMALL):
        self.pos = Vector2D(x, y)
        self.was_dropped = False
        self.picked_up = False
        self.cargo_type = cargo_type
        self.size = {
            CargoType.SMALL: config.CARGO_SMALL_SIZE,
            CargoType.MEDIUM: config.CARGO_MEDIUM_SIZE,
            CargoType.LARGE: config.CARGO_LARGE_SIZE,
        }[cargo_type]
        self.color = {
            CargoType.SMALL: config.CARGO_SMALL_COLOR,
            CargoType.MEDIUM: config.CARGO_MEDIUM_COLOR,
            CargoType.LARGE: config.CARGO_LARGE_COLOR,
        }[cargo_type]
        self.required_carriers = {CargoType.SMALL: 1, CargoType.MEDIUM: 2, CargoType.LARGE: 3}[cargo_type]
        self.carriers = []

    def draw(self, screen: pygame.Surface):
        x, y = int(self.pos.x), int(self.pos.y)
        rect = (x - self.size // 2, y - self.size // 2, self.size, self.size)
        pygame.draw.rect(screen, self.color, rect)
        outline_width = 3 if self.picked_up else 1
        pygame.draw.rect(screen, config.BLACK, rect, outline_width)
        if self.picked_up:
            pygame.draw.rect(screen, config.YELLOW, rect, 2)


class Obstacle:
    def __init__(self, x: int, y: int, width: int, height: int):
        self.rect = pygame.Rect(x, y, width, height)
        self.color = config.OBSTACLE_COLOR

    def draw(self, screen: pygame.Surface):
        pygame.draw.rect(screen, self.color, self.rect)
        pygame.draw.rect(screen, config.WHITE, self.rect, 2)


class Facility:
    def __init__(self, x: int, y: int, color, rate: float, symbol_points):
        half_size = config.FACILITY_SIZE // 2
        self.rect = pygame.Rect(x - half_size, y - half_size, config.FACILITY_SIZE, config.FACILITY_SIZE)
        self.color = color
        self.rate = rate
        self.symbol_points = symbol_points

    def process_drone(self, drone, dt: float, attr_name: str, max_attr: str):
        if self.rect.collidepoint(int(drone.pos.x), int(drone.pos.y)):
            setattr(drone, attr_name, min(getattr(drone, max_attr), getattr(drone, attr_name) + self.rate * dt))
            if getattr(drone, attr_name) >= getattr(drone, max_attr) * 0.95:
                drone.state = DroneState.IDLE
                drone.current_command = None
                setattr(drone, attr_name, getattr(drone, max_attr))

    def draw(self, screen: pygame.Surface):
        pygame.draw.rect(screen, self.color, self.rect)
        pygame.draw.rect(screen, config.BLACK, self.rect, 2)
        if self.symbol_points:
            pygame.draw.lines(screen, config.YELLOW, False, self.symbol_points, 3)


class ChargingStation(Facility):
    def __init__(self, x: int, y: int):
        super().__init__(
            x,
            y,
            config.CHARGING_STATION_COLOR,
            config.CHARGING_STATION_RATE,
            [(x - 5, y - 10), (x + 2, y), (x - 2, y), (x + 5, y + 10)],
        )

    def charge_drone(self, drone, dt: float):
        self.process_drone(drone, dt, "energy", "max_energy")


class Workshop(Facility):
    def __init__(self, x: int, y: int):
        super().__init__(x, y, config.WORKSHOP_COLOR, config.WORKSHOP_RATE, None)
        self.symbol_points = []

    def repair_drone(self, drone, dt: float):
        self.process_drone(drone, dt, "hp", "max_hp")

    def draw(self, screen: pygame.Surface):
        super().draw(screen)
        pygame.draw.circle(screen, config.BLACK, (self.rect.centerx, self.rect.centery), 8, 2)
        pygame.draw.line(
            screen,
            config.BLACK,
            (self.rect.centerx - 6, self.rect.centery - 6),
            (self.rect.centerx + 6, self.rect.centery + 6),
            2,
        )


class PathAvoidZone:
    def __init__(self, center_x: int, center_y: int, size: int):
        half = size // 2
        self.rect = pygame.Rect(int(center_x) - half, int(center_y) - half, size, size)
        self.avoid_only = True

    def draw(self, screen: pygame.Surface):
        return

