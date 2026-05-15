from typing import List

import config
from core.command import Command
from core.enums import CommandType, DroneState
from core.vector import Vector2D
from entities.drone import Drone


class CoordinatorDrone(Drone):
    def __init__(self, x: float, y: float):
        super().__init__(x, y)
        self.color = config.COORDINATOR_COLOR
        self.size = config.COORDINATOR_SIZE
        self.task_queue = []
        self.auction_in_progress = False

    def update(self, dt: float, drones: List, obstacles: List, objects: List = None, charging_stations: List = None, workshops: List = None):
        self.velocity = Vector2D(0, 0)
        self.acceleration = Vector2D(0, 0)
        for sensor in self.sensors.values():
            sensor.detect(self.pos, obstacles + drones)

    def analyze_and_delegate(self, drones: List[Drone], tasks: List[Command], charging_stations, workshops):
        for drone in drones:
            if drone == self:
                continue
            if drone.hp < config.HP_LOW and drone.state != DroneState.REPAIRING:
                target = self._pick_facility(drone, workshops, drones, DroneState.REPAIRING)
                if target:
                    self._reserve_slot(target, drones, DroneState.REPAIRING)
                    drone.current_command = Command(
                        CommandType.REPAIR, target_pos=(target.rect.centerx, target.rect.centery), priority=10
                    )
                    drone.state = DroneState.MOVING
            elif drone.energy < config.ENERGY_LOW and drone.state != DroneState.RECHARGING:
                target = self._pick_facility(drone, charging_stations, drones, DroneState.RECHARGING)
                if target:
                    self._reserve_slot(target, drones, DroneState.RECHARGING)
                    drone.current_command = Command(
                        CommandType.RECHARGE, target_pos=(target.rect.centerx, target.rect.centery), priority=9
                    )
                    drone.state = DroneState.MOVING

        if tasks and not self.auction_in_progress:
            self.run_auction(drones, tasks)
        self._manage_facilities(charging_stations, workshops, drones)

    def find_nearest(self, pos: Vector2D, objects: List):
        if not objects:
            return None
        nearest = None
        min_dist = float("inf")
        for obj in objects:
            if hasattr(obj, "rect"):
                dist = pos.distance_to(Vector2D(obj.rect.centerx, obj.rect.centery))
                if dist < min_dist:
                    nearest = obj
                    min_dist = dist
        return nearest

    def run_auction(self, drones: List[Drone], tasks: List[Command]):
        self.auction_in_progress = True
        available = []
        for d in drones:
            if d == self:
                continue
            if not getattr(d, "alive", True):
                continue
            if d.hp <= config.COORDINATOR_MIN_HP_FOR_TASK or d.energy <= config.COORDINATOR_MIN_ENERGY_FOR_TASK:
                continue
            if d.state in (
                DroneState.RECHARGING,
                DroneState.REPAIRING,
                DroneState.CARRYING,
                DroneState.MOVING,
                DroneState.EXECUTING,
            ):
                continue
            if d.state == DroneState.IDLE and d.current_command is None:
                available.append(d)
        if not available or not tasks:
            self.auction_in_progress = False
            return

        for task in tasks[:]:
            if not available:
                break
            if task.cmd_type == CommandType.PICK_UP and getattr(task.target_object, "required_carriers", 1) > 1:
                needed = task.target_object.required_carriers
                chosen = self._select_best(available, task, limit=needed)
                if len(chosen) == needed:
                    for drone in chosen:
                        drone.current_command = task
                        drone.state = DroneState.MOVING
                        available.remove(drone)
                    tasks.remove(task)
                continue
            best_drone = None
            best_bid = float("inf")
            for drone in available:
                bid = self.calculate_bid(drone, task)
                if bid < best_bid:
                    best_bid = bid
                    best_drone = drone
            if best_drone:
                best_drone.current_command = task
                best_drone.state = DroneState.MOVING
                available.remove(best_drone)
                tasks.remove(task)
        self.auction_in_progress = False

    def _select_best(self, candidates: List[Drone], task: Command, limit: int):
        scored = [(self.calculate_bid(d, task), d) for d in candidates]
        scored.sort(key=lambda x: x[0])
        return [d for _, d in scored[:limit]]

    def _pick_facility(self, drone: Drone, facilities, drones: List[Drone], state: DroneState):
        candidates = []
        for fac in facilities:
            load = sum(
                1 for d in drones
                if d.state == state and fac.rect.collidepoint(int(d.pos.x), int(d.pos.y))
            )
            dist = drone.pos.distance_to(Vector2D(fac.rect.centerx, fac.rect.centery))
            candidates.append((load, dist, fac))
        if not candidates:
            return None
        candidates.sort(key=lambda x: (x[0], x[1]))
        return candidates[0][2]

    def _manage_facilities(self, charging_stations, workshops, drones: List[Drone]):
        coord_pos = (self.pos.x, self.pos.y)
        for station in charging_stations:
            self._balance_facility(station, drones, DroneState.RECHARGING, "energy", coord_pos)
        for workshop in workshops:
            self._balance_facility(workshop, drones, DroneState.REPAIRING, "hp", coord_pos)

    def _balance_facility(self, facility, drones: List[Drone], state: DroneState, attr: str, coord_pos):
        inside = [
            d for d in drones
            if facility.rect.collidepoint(int(d.pos.x), int(d.pos.y)) and d.state == state
        ]
        if len(inside) <= 2:
            return
        inside.sort(key=lambda d: getattr(d, attr), reverse=True)
        to_leave = inside[2:]
        for drone in to_leave:
            target = drone.spawn_pos.as_tuple() if hasattr(drone, "spawn_pos") else coord_pos
            drone.current_command = Command(CommandType.MOVE_TO, target)
            drone.state = DroneState.MOVING

    def _reserve_slot(self, facility, drones: List[Drone], state: DroneState, needed: int = 1):
        inside = [
            d for d in drones
            if facility.rect.collidepoint(int(d.pos.x), int(d.pos.y)) and d.state == state
        ]
        extra = max(0, len(inside) + needed - 2)
        if extra <= 0:
            return
        inside.sort(key=lambda d: getattr(d, "hp" if state == DroneState.REPAIRING else "energy"), reverse=True)
        for drone in inside[:extra]:
            target = drone.spawn_pos.as_tuple() if hasattr(drone, "spawn_pos") else (facility.rect.centerx, facility.rect.centery)
            drone.current_command = Command(CommandType.MOVE_TO, target)
            drone.state = DroneState.MOVING

    def calculate_bid(self, drone: Drone, task: Command) -> float:
        if not task.target_pos:
            return float("inf")
        target = Vector2D(*task.target_pos)
        distance_cost = drone.pos.distance_to(target) * config.COORDINATOR_BID_DISTANCE_WEIGHT
        energy_cost = (config.DRONE_MAX_ENERGY - drone.energy) * config.COORDINATOR_BID_ENERGY_WEIGHT
        hp_cost = (config.DRONE_MAX_HP - drone.hp) * config.COORDINATOR_BID_HP_WEIGHT
        priority_cost = (10 - task.priority) * config.COORDINATOR_BID_PRIORITY_WEIGHT
        return distance_cost + energy_cost + hp_cost + priority_cost

    def draw(self, screen):
        super().draw(screen)
        x, y = int(self.pos.x), int(self.pos.y)
        import pygame

        pygame.draw.circle(screen, config.PURPLE, (x, y), self.size + 4, 2)