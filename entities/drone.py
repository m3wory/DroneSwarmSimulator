import math
import random
from typing import List, Optional, Tuple

import pygame

import config
from core.command import Command
from core.enums import CommandType, DroneState
from core.pathfinding import AStarPathfinder
from core.vector import Vector2D
from entities.objects import CargoType


class Sensor:
    def __init__(self, sensor_type: str, range_val: float):
        self.type = sensor_type
        self.range = range_val
        self.detected_objects = []

    def detect(self, pos: Vector2D, objects: List):
        self.detected_objects = [
            (obj, pos.distance_to(obj.pos))
            for obj in objects
            if hasattr(obj, "pos") and pos.distance_to(obj.pos) <= self.range
        ]
        return self.detected_objects


class Drone:
    drone_id_counter = 0

    def __init__(self, x: float, y: float):
        self.id = Drone.drone_id_counter
        Drone.drone_id_counter += 1
        self.pos = Vector2D(x, y)
        self.spawn_pos = Vector2D(x, y)
        self.velocity = Vector2D(0, 0)
        self.acceleration = Vector2D(0, 0)
        self.hp = config.DRONE_MAX_HP
        self.max_hp = config.DRONE_MAX_HP
        self.energy = config.DRONE_MAX_ENERGY
        self.max_energy = config.DRONE_MAX_ENERGY
        self.speed = config.DRONE_SPEED
        self.max_speed = config.DRONE_MAX_SPEED
        self.max_force = config.DRONE_MAX_FORCE
        self.motion_alpha = config.DRONE_MOTION_ALPHA
        self.formation_alpha = config.DRONE_FORMATION_ALPHA
        self.alive = True
        self.sensors = {
            "proximity": Sensor("proximity", config.SENSOR_PROXIMITY_RANGE),
            "object_detector": Sensor("object_detector", config.SENSOR_OBJECT_DETECTOR_RANGE),
            "collision": Sensor("collision", config.SENSOR_COLLISION_RANGE),
        }
        self.state = DroneState.IDLE
        self.selected = False
        self.carrying = None
        self.current_command: Optional[Command] = None
        self.path: List[Vector2D] = []
        self.path_index = 0
        self.perception_radius = config.DRONE_PERCEPTION_RADIUS
        self.separation_radius = config.DRONE_SEPARATION_RADIUS
        self.size = config.DRONE_SIZE
        self.color = config.DRONE_COLOR
        self.collect_timer = 0
        self.distance_traveled = 0.0
        self.last_collision_time = 0.0
        self.executing_since = None

    def apply_force(self, force: Vector2D):
        self.acceleration = self.acceleration + force

    def update(self, dt: float, drones: List, obstacles: List):
        drain = config.ENERGY_DRAIN_RATE * self._energy_drain_factor()
        self.energy = max(0, self.energy - drain * dt)
        if random.random() < config.HP_DAMAGE_CHANCE:
            self.hp = max(0, self.hp - config.HP_DAMAGE_AMOUNT)

        if self.hp <= 0 or self.energy <= 0:
            self.die()
            return

        self._handle_obstacles(obstacles)
        self._handle_drone_collisions(drones)

        for sensor in self.sensors.values():
            sensor.detect(self.pos, obstacles + drones)
        if self.state == DroneState.EXECUTING and self.executing_since is not None:
            try:
                current_time = pygame.time.get_ticks() / 1000.0
            except Exception:
                import time

                current_time = time.time()
            if current_time - self.executing_since > 10.0:
                self._abort_executing()

        if self.current_command:
            self.execute_command(drones, obstacles)
        self._maybe_lift_cargo()
        self._sync_cargo_command()

        desired = (self.velocity + self.acceleration).limit(self.max_speed)
        alpha = self.formation_alpha if self._in_formation() else self.motion_alpha
        self.velocity = Vector2D(
            self.velocity.x * (1 - alpha) + desired.x * alpha,
            self.velocity.y * (1 - alpha) + desired.y * alpha,
        ).limit(self.max_speed)
        old_pos = Vector2D(self.pos.x, self.pos.y)
        self.pos = self.pos + self.velocity
        try:
            from metrics import add_distance

            dist = old_pos.distance_to(self.pos)
            self.distance_traveled += dist
            add_distance(dist)
        except Exception:
            pass
        self.acceleration = Vector2D(0, 0)
        self.pos.x = max(10, min(config.SCREEN_WIDTH - 10, self.pos.x))
        self.pos.y = max(10, min(config.SCREEN_HEIGHT - 10, self.pos.y))

    def _in_formation(self):
        return self.current_command and getattr(self.current_command, "cmd_type", None) == CommandType.FORMATION

    def _energy_drain_factor(self):
        if self.state == DroneState.RECHARGING:
            return config.ENERGY_DRAIN_RECHARGING
        if self.state == DroneState.CARRYING:
            return config.ENERGY_DRAIN_CARRYING
        if self.state == DroneState.REPAIRING:
            return config.ENERGY_DRAIN_REPAIRING
        if self.state in (DroneState.MOVING, DroneState.EXECUTING):
            return config.ENERGY_DRAIN_MOVING
        return config.ENERGY_DRAIN_IDLE

    def _carry_speed_factor(self):
        if not self.carrying or not getattr(self.carrying, "picked_up", False):
            return 1.0
        cargo = getattr(self.carrying, "cargo_type", CargoType.SMALL)
        return {
            CargoType.SMALL: config.CARGO_SPEED_SMALL,
            CargoType.MEDIUM: config.CARGO_SPEED_MEDIUM,
            CargoType.LARGE: config.CARGO_SPEED_LARGE,
        }.get(cargo, 1.0)

    def _handle_obstacles(self, obstacles):
        for obstacle in obstacles:
            if hasattr(obstacle, "rect"):
                obs_pos = Vector2D(obstacle.rect.centerx, obstacle.rect.centery)
                dist = self.pos.distance_to(obs_pos)
                collision_dist = config.COLLISION_DIST + max(obstacle.rect.width, obstacle.rect.height) / 2
                if dist < collision_dist and self.velocity.length() > 1:
                    if not getattr(obstacle, "avoid_only", False):
                        self.hp = max(0, self.hp - config.COLLISION_DAMAGE)
                    self.pos = self.pos + (self.pos - obs_pos).normalize() * 2

    def _handle_drone_collisions(self, drones):
        for drone in drones:
            if drone == self:
                continue
            same_cargo = False
            if getattr(self, "carrying", None) is not None and getattr(drone, "carrying", None) is not None:
                try:
                    if self.carrying is drone.carrying:
                        same_cargo = True
                except Exception:
                    same_cargo = False

            dist = self.pos.distance_to(drone.pos)
            if same_cargo:
                effective_dist = max(1.0, (self.size + drone.size) * 0.9)
                if dist < effective_dist:
                    diff = self.pos - drone.pos
                    push = diff.normalize() * 0.5 if diff.length() > 0 else Vector2D(0, 0)
                    self.pos = self.pos + push
            else:
                collision_limit = self.size + drone.size + 5
                if dist < collision_limit:
                    try:
                        current_time = pygame.time.get_ticks() / 1000.0
                    except Exception:
                        import time

                        current_time = time.time()

                    last_pair_time = max(getattr(self, "last_collision_time", 0.0), getattr(drone, "last_collision_time", 0.0))
                    if current_time - last_pair_time > config.COLLISION_COOLDOWN:
                        try:
                            from metrics import increment_collision

                            increment_collision()
                        except Exception:
                            pass
                        self.last_collision_time = current_time
                        drone.last_collision_time = current_time

                    if self.velocity.length() > 0.5:
                        self.hp = max(0, self.hp - config.DRONE_COLLISION_DAMAGE)
                    diff = self.pos - drone.pos
                    push = diff.normalize() * 1.5 if diff.length() > 0 else Vector2D(0, 0)
                    self.pos = self.pos + push

    def execute_command(self, drones: List, obstacles: List):
        cmd = self.current_command
        handlers = {
            CommandType.MOVE_TO: lambda: self.move_to_target(cmd.target_pos, obstacles, drones),
            CommandType.PICK_UP: lambda: self._handle_pickup(cmd, drones, obstacles),
            CommandType.DROP_OBJECT: self._handle_drop,
            CommandType.RECHARGE: lambda: self._handle_facility(cmd, drones, obstacles, DroneState.RECHARGING),
            CommandType.REPAIR: lambda: self._handle_facility(cmd, drones, obstacles, DroneState.REPAIRING),
            CommandType.FORMATION: lambda: self._handle_formation(cmd, drones, obstacles),
        }
        handlers.get(cmd.cmd_type, lambda: None)()

    def _handle_pickup(self, cmd, drones, obstacles):
        if not cmd.target_object or self.carrying or getattr(cmd.target_object, "picked_up", False):
            self._clear_command()
            return
        dist = self.pos.distance_to(cmd.target_object.pos)
        if dist < config.PICKUP_DIST:
            obj = cmd.target_object
            if self not in obj.carriers:
                obj.carriers.append(self)
            if len(obj.carriers) >= obj.required_carriers:
                obj.picked_up = True
                try:
                    obj.was_dropped = False
                except Exception:
                    pass
                for carrier in obj.carriers:
                    carrier.carrying = obj
                    carrier.state = DroneState.CARRYING
                    carrier.current_command = None
                    carrier.velocity = Vector2D(0, 0)
                    carrier.acceleration = Vector2D(0, 0)
                    carrier.path = []
                    carrier.path_index = 0
                    try:
                        carrier.executing_since = None
                    except Exception:
                        pass
            else:
                self.carrying = obj
                self.state = DroneState.EXECUTING
                self.current_command = None
                self.velocity = Vector2D(0, 0)
                try:
                    self.executing_since = pygame.time.get_ticks() / 1000.0
                except Exception:
                    import time

                    self.executing_since = time.time()
        else:
            self.move_to_target(cmd.target_object.pos.as_tuple(), obstacles, drones)

    def _handle_drop(self):
        if self.carrying:
            cargo = self.carrying
            carriers_snapshot = list(getattr(cargo, "carriers", []))

            if carriers_snapshot:
                avg_x = sum(d.pos.x for d in carriers_snapshot) / len(carriers_snapshot)
                avg_y = sum(d.pos.y for d in carriers_snapshot) / len(carriers_snapshot)
                cargo.pos = Vector2D(avg_x, avg_y)
                cargo.picked_up = False

                for d in carriers_snapshot:
                    d.carrying = None
                    d.state = DroneState.IDLE
                    d.current_command = None
                    d.velocity = Vector2D(0, 0)
                    d.acceleration = Vector2D(0, 0)

                cargo.carriers.clear()
                cargo.was_dropped = True
            else:
                cargo.pos = Vector2D(self.pos.x, self.pos.y)
                cargo.picked_up = False
                cargo.was_dropped = True

            self.carrying = None
            self.state = DroneState.IDLE
            self.current_command = None
            self.velocity = Vector2D(0, 0)
            self.acceleration = Vector2D(0, 0)

    def _handle_facility(self, cmd, drones, obstacles, state):
        target_pos = Vector2D(*cmd.target_pos)
        if self.pos.distance_to(target_pos) > config.CHARGE_DIST:
            self.move_to_target(cmd.target_pos, obstacles, drones)
        else:
            self.state = state
            self.velocity = self.velocity * 0.7

    def _handle_formation(self, cmd, drones, obstacles):
        self.apply_boids_behavior(drones, obstacles)
        if not cmd.target_pos:
            return
        target = Vector2D(*cmd.target_pos)
        group = [
            d
            for d in drones
            if d.current_command and d.current_command.cmd_type == CommandType.FORMATION and d.current_command == cmd
        ]
        if group:
            avg_pos = sum((d.pos for d in group), Vector2D(0, 0)) / len(group)
            total_dist = sum(d.pos.distance_to(avg_pos) for d in group)
            tolerance = config.FORMATION_GROUP_TOLERANCE * len(group)
            if total_dist <= tolerance and avg_pos.distance_to(target) < config.FORMATION_ARRIVAL_DISTANCE:
                self.velocity = self.velocity * 0.8
            else:
                steer = (target - self.pos).normalize() * self.max_speed - self.velocity
                self.apply_force(steer.limit(self.max_force * 0.3))
        elif self.pos.distance_to(target) > 20:
            steer = (target - self.pos).normalize() * self.max_speed - self.velocity
            self.apply_force(steer.limit(self.max_force * 0.5))

    def move_to_target(self, target_pos: Tuple[float, float], obstacles: List, drones: List = None):
        target = Vector2D(*target_pos)
        distance = self.pos.distance_to(target)

        if distance < 4:
            self.pos = target
            self.velocity = Vector2D(0, 0)
            if self.current_command and self.current_command.cmd_type == CommandType.MOVE_TO:
                self._clear_command()
            return

        if not self.path or random.random() < config.PATH_UPDATE_CHANCE:
            new_path = AStarPathfinder().find_path(self.pos, target, obstacles)
            if new_path:
                self.path = new_path
                self.path_index = 0

        def _dir(v):
            return v.normalize() if v.length() > 0 else Vector2D(0, 0)

        if self.path and self.path_index < len(self.path):
            waypoint = self.path[self.path_index]
            dist_to_waypoint = self.pos.distance_to(waypoint)
            snap_threshold = max(6, self.max_speed)
            if dist_to_waypoint < snap_threshold:
                self.pos = Vector2D(waypoint.x, waypoint.y)
                self.velocity = Vector2D(0, 0)
                self.path_index += 1
                if self.path_index >= len(self.path):
                    self.path = []
                    self.path_index = 0
            elif dist_to_waypoint < 14:
                self.path_index += 1
                if self.path_index >= len(self.path):
                    self.path = []
                    self.path_index = 0
            else:
                to_wp = (waypoint - self.pos)
                desired_dir = _dir(to_wp)
                vel_dir = _dir(self.velocity) if self.velocity.length() > 0 else desired_dir
                cos_angle = max(-1.0, min(1.0, vel_dir.x * desired_dir.x + vel_dir.y * desired_dir.y))
                if cos_angle < 0.5:
                    turn_scale = 0.45
                elif cos_angle < 0.85:
                    turn_scale = 0.75
                else:
                    turn_scale = 1.0

                is_final = self.path_index >= len(self.path) - 1
                dist_scale = 1.0
                if is_final:
                    slow_radius_final = 40
                    if dist_to_waypoint < slow_radius_final:
                        dist_scale = max(0.28, dist_to_waypoint / slow_radius_final)

                speed_scale = turn_scale * dist_scale
                desired = desired_dir * (self.max_speed * self._carry_speed_factor() * speed_scale)
                if drones:
                    sep = self.separate(drones)
                    if sep.length() > 0:
                        desired = desired + sep * 0.6
                self.velocity = desired.limit(self.max_speed * self._carry_speed_factor())
                self.acceleration = Vector2D(0, 0)
        else:
            to_target = (target - self.pos)
            desired_dir = _dir(to_target)
            vel_dir = _dir(self.velocity) if self.velocity.length() > 0 else desired_dir
            cos_angle = max(-1.0, min(1.0, vel_dir.x * desired_dir.x + vel_dir.y * desired_dir.y))
            if cos_angle < 0.5:
                turn_scale = 0.45
            elif cos_angle < 0.85:
                turn_scale = 0.75
            else:
                turn_scale = 1.0
            slow_radius_final = 40
            dist_scale = 1.0
            if distance < slow_radius_final:
                dist_scale = max(0.28, distance / slow_radius_final)
            speed_scale = turn_scale * dist_scale
            desired = desired_dir * (self.max_speed * self._carry_speed_factor() * speed_scale)
            snap_threshold = max(6, self.max_speed)
            if distance < snap_threshold:
                self.pos = Vector2D(target.x, target.y)
                self.velocity = Vector2D(0, 0)
                if self.current_command and self.current_command.cmd_type == CommandType.MOVE_TO:
                    self._clear_command()
            else:
                if drones:
                    sep = self.separate(drones)
                    if sep.length() > 0:
                        desired = desired + sep * 0.6
                self.velocity = desired.limit(self.max_speed * self._carry_speed_factor())
                self.acceleration = Vector2D(0, 0)

    def _maybe_lift_cargo(self):
        if self.carrying and not getattr(self.carrying, "picked_up", False):
            cargo = self.carrying
            if len(cargo.carriers) >= cargo.required_carriers:
                cargo.picked_up = True
                try:
                    cargo.was_dropped = False
                except Exception:
                    pass
                for carrier in cargo.carriers:
                    carrier.state = DroneState.CARRYING
                    carrier.current_command = carrier.current_command or self.current_command
                    try:
                        carrier.executing_since = None
                    except Exception:
                        pass

    def _sync_cargo_command(self):
        if not self.carrying or not getattr(self.carrying, "picked_up", False):
            return
        cargo = self.carrying
        leader_cmd = next((d.current_command for d in cargo.carriers if d.current_command), None)
        if not leader_cmd:
            return
        for carrier in cargo.carriers:
            if carrier.current_command != leader_cmd:
                carrier.current_command = leader_cmd
                if leader_cmd.cmd_type == CommandType.MOVE_TO:
                    carrier.state = DroneState.CARRYING

    def _clear_command(self):
        self.current_command = None
        if self.carrying and getattr(self.carrying, "picked_up", False):
            self.state = DroneState.CARRYING
        else:
            self.state = DroneState.IDLE
        self.path = []
        self.path_index = 0
        self.velocity = Vector2D(0, 0)
        self.acceleration = Vector2D(0, 0)
        try:
            self.executing_since = None
        except Exception:
            pass

    def die(self):
        if self.carrying:
            self.carrying.pos = Vector2D(self.pos.x, self.pos.y)
            self.carrying.picked_up = False
            try:
                self.carrying.was_dropped = True
            except Exception:
                pass
            self.carrying = None
        self.current_command = None
        self.state = DroneState.IDLE
        self.velocity = Vector2D(0, 0)
        self.acceleration = Vector2D(0, 0)
        try:
            self.executing_since = None
        except Exception:
            pass
        self.alive = False
        try:
            from metrics import increment_dead

            increment_dead()
        except Exception:
            pass

    def _abort_executing(self):
        try:
            if self.carrying and hasattr(self.carrying, "carriers"):
                try:
                    if self in self.carrying.carriers:
                        self.carrying.carriers.remove(self)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self.carrying = None
        except Exception:
            pass
        self.current_command = None
        self.state = DroneState.IDLE
        self.path = []
        self.path_index = 0
        self.velocity = Vector2D(0, 0)
        self.acceleration = Vector2D(0, 0)
        try:
            self.executing_since = None
        except Exception:
            pass

    def apply_boids_behavior(self, drones: List, obstacles: List):
        behaviors = [
            (self.separate(drones), config.BOIDS_SEPARATION_WEIGHT),
            (self.align(drones), config.BOIDS_ALIGN_WEIGHT),
            (self.cohere(drones), config.BOIDS_COHESION_WEIGHT),
            (self.avoid_obstacles(obstacles), config.BOIDS_OBSTACLE_AVOIDANCE_WEIGHT),
            (self.avoid_edges(), config.BOIDS_EDGE_AVOIDANCE_WEIGHT),
        ]
        for force, weight in behaviors:
            self.apply_force(force * weight)

    def avoid_edges(self) -> Vector2D:
        margin = config.BOIDS_EDGE_MARGIN
        steer = Vector2D(0, 0)
        if self.pos.x < margin:
            steer = steer + Vector2D(1, 0) * ((margin - self.pos.x) / margin)
        if self.pos.x > config.SCREEN_WIDTH - margin:
            steer = steer + Vector2D(-1, 0) * ((self.pos.x - (config.SCREEN_WIDTH - margin)) / margin)
        if self.pos.y < margin:
            steer = steer + Vector2D(0, 1) * ((margin - self.pos.y) / margin)
        if self.pos.y > config.SCREEN_HEIGHT - margin:
            steer = steer + Vector2D(0, -1) * ((self.pos.y - (config.SCREEN_HEIGHT - margin)) / margin)
        if steer.length() == 0:
            return Vector2D(0, 0)
        steer = steer.normalize() * self.max_speed - self.velocity
        return steer.limit(self.max_force * 1.5)

    def separate(self, drones: List) -> Vector2D:
        steer = Vector2D(0, 0)
        count = 0
        for drone in drones:
            if drone == self:
                continue
            dist = self.pos.distance_to(drone.pos)
            if 0 < dist < self.separation_radius:
                steer = steer + (self.pos - drone.pos).normalize() / dist
                count += 1
        if count == 0:
            return Vector2D(0, 0)
        steer = (steer / count).normalize() * self.max_speed - self.velocity
        return steer.limit(self.max_force)

    def align(self, drones: List) -> Vector2D:
        sum_vel = Vector2D(0, 0)
        count = 0
        for drone in drones:
            if drone == self:
                continue
            dist = self.pos.distance_to(drone.pos)
            if 0 < dist < self.perception_radius:
                sum_vel = sum_vel + drone.velocity
                count += 1
        if count == 0:
            return Vector2D(0, 0)
        sum_vel = (sum_vel / count).normalize() * self.max_speed - self.velocity
        return sum_vel.limit(self.max_force)

    def cohere(self, drones: List) -> Vector2D:
        sum_pos = Vector2D(0, 0)
        count = 0
        for drone in drones:
            if drone == self:
                continue
            dist = self.pos.distance_to(drone.pos)
            if 0 < dist < self.perception_radius:
                sum_pos = sum_pos + drone.pos
                count += 1
        return self.seek(sum_pos / count) if count > 0 else Vector2D(0, 0)

    def avoid_obstacles(self, obstacles: List) -> Vector2D:
        steer = Vector2D(0, 0)
        count = 0
        for obstacle in obstacles:
            if hasattr(obstacle, "rect"):
                obs_pos = Vector2D(obstacle.rect.centerx, obstacle.rect.centery)
                dist = self.pos.distance_to(obs_pos)
                if 0 < dist < config.BOIDS_OBSTACLE_AVOIDANCE_DISTANCE:
                    steer = steer + (self.pos - obs_pos).normalize() / dist
                    count += 1
        if count == 0:
            return Vector2D(0, 0)
        steer = (steer / count).normalize() * self.max_speed - self.velocity
        return steer.limit(self.max_force)

    def seek(self, target: Vector2D) -> Vector2D:
        desired = (target - self.pos).normalize() * self.max_speed
        return (desired - self.velocity).limit(self.max_force)

    def draw(self, screen: pygame.Surface):
        x, y = int(self.pos.x), int(self.pos.y)
        if self.selected:
            pygame.draw.circle(screen, config.YELLOW, (x, y), self.size + config.SELECTION_CIRCLE_OFFSET, 2)
        color = config.RED if self.hp < config.HP_LOW else (config.ORANGE if self.energy < config.ENERGY_LOW else self.color)
        pygame.draw.circle(screen, color, (x, y), self.size)
        if self.velocity.length() > 0.1:
            end = (
                int(x + self.velocity.x * config.VELOCITY_VISUALIZATION_SCALE),
                int(y + self.velocity.y * config.VELOCITY_VISUALIZATION_SCALE),
            )
            pygame.draw.line(screen, config.DARK_GRAY, (x, y), end, 2)
        if self.carrying and getattr(self.carrying, "picked_up", False):
            cargo_pos = (int(self.carrying.pos.x), int(self.carrying.pos.y))
            pygame.draw.line(screen, config.DARK_GRAY, (x, y), cargo_pos, 2)
        if self.path and self.path_index < len(self.path):
            max_waypoints = min(len(self.path), self.path_index + config.PATH_VISIBLE_WAYPOINTS)
            for i in range(self.path_index, max_waypoints):
                wp = self.path[i]
                pygame.draw.circle(screen, config.CYAN, (int(wp.x), int(wp.y)), config.PATH_WAYPOINT_RADIUS)
        font = pygame.font.Font(None, 16)
        screen.blit(font.render(str(self.id), True, config.BLACK), (x - 5, y - config.DRONE_ID_OFFSET_Y))

