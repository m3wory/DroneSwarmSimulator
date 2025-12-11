import math
from typing import List, Tuple, Optional

import pygame

import config
from core.command import Command
from core.enums import CommandType, DroneState, EditorMode
from core.vector import Vector2D
from entities.coordinator import CoordinatorDrone
from entities.drone import Drone
from entities.objects import ChargingStation, GameObject, Obstacle, Workshop, CargoType, PathAvoidZone
from ui.ui import UI


class DroneSwarmSimulator:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
        pygame.display.set_caption("Drone Swarm Simulator - Editor Mode")
        self.clock = pygame.time.Clock()
        self.running = True
        self.paused = False
        self.drones: List[Drone] = []
        self.coordinator: Optional[CoordinatorDrone] = None
        self.objects: List[GameObject] = []
        self.obstacles: List[Obstacle] = []
        self.charging_stations: List[ChargingStation] = []
        self.workshops: List[Workshop] = []
        self.ui = UI()
        self.selected_drones: List[Drone] = []
        self.drag_start = None
        self.drag_rect = None
        self.editor_mode = EditorMode.NONE
        self.pending_tasks: List[Command] = []
        self.sim_time = 0.0
        self._picked_objects_seen = set()
        self.initialize_world()

    def initialize_world(self):
        self.coordinator = CoordinatorDrone(config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT // 2)
        self.drones.append(self.coordinator)
        for i in range(config.INITIAL_DRONE_COUNT):
            angle = (i / config.INITIAL_DRONE_COUNT) * 2 * math.pi
            x = config.SCREEN_WIDTH // 2 + math.cos(angle) * config.INITIAL_DRONE_SPAWN_RADIUS
            y = config.SCREEN_HEIGHT // 2 + math.sin(angle) * config.INITIAL_DRONE_SPAWN_RADIUS
            self.drones.append(Drone(x, y))
        self.charging_stations = []
        self.workshops = []
        try:
            total_facilities = 6
            margin_x = 80
            y = config.SCREEN_HEIGHT - 60
            usable_width = max(200, config.SCREEN_WIDTH - 2 * margin_x)
            for i in range(total_facilities):
                x = int(margin_x + (i * (usable_width) / max(1, total_facilities - 1)))
                if i % 2 == 0:
                    self.workshops.append(Workshop(x, y))
                else:
                    self.charging_stations.append(ChargingStation(x, y))
        except Exception:
            self.charging_stations = [ChargingStation(x, y) for x, y in config.INITIAL_CHARGING_STATIONS]
            self.workshops = [Workshop(x, y) for x, y in config.INITIAL_WORKSHOPS]
        import pygame as _pg
        lx, ly, lw, lh = config.LOAD_ZONE_RECT
        ux, uy, uw, uh = config.UNLOAD_ZONE_RECT
        self.load_zone_rect = _pg.Rect(lx, ly, lw, lh)
        self.unload_zone_rect = _pg.Rect(ux, uy, uw, uh)

        import random as _rand
        total = 0
        unload_spots = []
        try:
            n_spots = max(1, config.UNLOAD_SUBSPOTS)
        except Exception:
            n_spots = 6
        if n_spots == 1:
            unload_spots.append(Vector2D(self.unload_zone_rect.centerx, self.unload_zone_rect.centery))
        else:
            ly2 = self.unload_zone_rect.top + 10
            hy = self.unload_zone_rect.bottom - 10
            for i in range(n_spots):
                y = ly2 + i * (hy - ly2) / max(1, n_spots - 1)
                x = self.unload_zone_rect.centerx
                unload_spots.append(Vector2D(int(x), int(y)))

        def _spawn(n, cargo_type):
            nonlocal total
            for _ in range(n):
                rx = _rand.randint(self.load_zone_rect.left + 10, self.load_zone_rect.right - 10)
                ry = _rand.randint(self.load_zone_rect.top + 10, self.load_zone_rect.bottom - 10)
                obj = GameObject(rx, ry, cargo_type)
                # assign destination among unload subspots round-robin
                idx = total % len(unload_spots)
                obj.destination_pos = unload_spots[idx]
                obj.delivered = False
                self.objects.append(obj)
                self.pending_tasks.append(Command(CommandType.PICK_UP, (int(obj.pos.x), int(obj.pos.y)), obj))
                total += 1
        _spawn(config.INITIAL_CARGO_SMALL, CargoType.SMALL)
        _spawn(config.INITIAL_CARGO_MEDIUM, CargoType.MEDIUM)
        _spawn(config.INITIAL_CARGO_LARGE, CargoType.LARGE)

        try:
            from metrics import set_transport_total

            set_transport_total(total)
        except Exception:
            pass

        cx, cy = config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT // 2

        try:
            size = config.OBSTACLE_DEFAULT_SIZE
            positions = [
                (cx - 220, cy),
                (cx - 80, cy - 100),
                (cx + 80, cy + 100),
                (cx + 220, cy),
                (cx, cy + 180),
            ]
            for (ox, oy) in positions:
                self.obstacles.append(Obstacle(ox - size // 2, oy - size // 2, size, size))
            try:
                zone_size = getattr(config, "COORDINATOR_AVOID_ZONE_SIZE", 160)
                self.obstacles.append(PathAvoidZone(cx, cy, zone_size))
            except Exception:
                pass
        except Exception:
            pass

        try:
            n_form = min(config.FORMATION_DRONE_COUNT, max(0, len(self.drones) - 1))
            formation_cmd = Command(CommandType.FORMATION, (cx, cy))
            formation_cmd.group_size = n_form
            assigned = 0
            for d in list(self.drones):
                if d is self.coordinator:
                    continue
                if assigned >= n_form:
                    break
                d.current_command = formation_cmd
                d.state = DroneState.MOVING
                assigned += 1
        except Exception:
            pass

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    self._handle_left_click(event.pos)
                elif event.button == 3:
                    self._handle_right_click(event.pos)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self._handle_drag_release(event.pos)
            elif event.type == pygame.MOUSEMOTION and event.buttons[0] and self.drag_start:
                if self.editor_mode == EditorMode.NONE:
                    self.drag_rect = pygame.Rect(
                        min(self.drag_start[0], event.pos[0]),
                        min(self.drag_start[1], event.pos[1]),
                        abs(event.pos[0] - self.drag_start[0]),
                        abs(event.pos[1] - self.drag_start[1]),
                    )
            elif event.type == pygame.KEYDOWN:
                self._handle_keyboard(event.key, pygame.mouse.get_pos())

    def _handle_left_click(self, pos: Tuple[int, int]):
        if self.ui.info_panel_toggle_rect.collidepoint(pos):
            self.ui.info_panel_collapsed = not self.ui.info_panel_collapsed
            return
        if self.ui.info_panel_rect.collidepoint(pos):
            return

        if self.ui.editor_menu_open:
            menu_rect = pygame.Rect(
                config.SCREEN_WIDTH - config.EDITOR_MENU_X_OFFSET,
                config.EDITOR_MENU_Y_OFFSET,
                config.EDITOR_MENU_WIDTH,
                len(self.ui.editor_menu_items) * config.CONTEXT_MENU_ITEM_HEIGHT,
            )
            if menu_rect.collidepoint(pos):
                self._handle_editor_menu_click(pos)
            elif self.editor_mode != EditorMode.NONE:
                self._handle_editor_click(pos)
        elif self.ui.context_menu_open:
            self._handle_context_menu_click(pos)
        elif self.editor_mode != EditorMode.NONE:
            self._handle_editor_click(pos)
        else:
            self._handle_drone_selection(pos)

    def _handle_right_click(self, pos: Tuple[int, int]):
        if not self.ui.editor_menu_open:
            self.ui.context_menu_open = True
            self.ui.context_menu_pos = pos

    def _handle_editor_menu_click(self, pos: Tuple[int, int]):
        menu_rect = pygame.Rect(
            config.SCREEN_WIDTH - config.EDITOR_MENU_X_OFFSET,
            config.EDITOR_MENU_Y_OFFSET,
            config.EDITOR_MENU_WIDTH,
            len(self.ui.editor_menu_items) * config.CONTEXT_MENU_ITEM_HEIGHT,
        )
        if not menu_rect.collidepoint(pos):
            return
        item_index = (pos[1] - menu_rect.y) // config.CONTEXT_MENU_ITEM_HEIGHT
        if 0 <= item_index < len(self.ui.editor_menu_items):
            self.editor_mode = self.ui.editor_menu_items[item_index][1]

    def _handle_editor_click(self, pos: Tuple[int, int]):
        editor_actions = {
            EditorMode.ADD_OBSTACLE: lambda: self.obstacles.append(
                Obstacle(
                    pos[0] - config.OBSTACLE_DEFAULT_SIZE // 2,
                    pos[1] - config.OBSTACLE_DEFAULT_SIZE // 2,
                    config.OBSTACLE_DEFAULT_SIZE,
                    config.OBSTACLE_DEFAULT_SIZE,
                )
            ),
            EditorMode.ADD_CHARGING_STATION: lambda: self.charging_stations.append(ChargingStation(pos[0], pos[1])),
            EditorMode.ADD_WORKSHOP: lambda: self.workshops.append(Workshop(pos[0], pos[1])),
            EditorMode.ADD_OBJECT: lambda: self._spawn_cargo_cycle(pos),
            EditorMode.ADD_OBJECT_SMALL: lambda: self.objects.append(GameObject(pos[0], pos[1], CargoType.SMALL)),
            EditorMode.ADD_OBJECT_MEDIUM: lambda: self.objects.append(GameObject(pos[0], pos[1], CargoType.MEDIUM)),
            EditorMode.ADD_OBJECT_LARGE: lambda: self.objects.append(GameObject(pos[0], pos[1], CargoType.LARGE)),
            EditorMode.DELETE: lambda: self._delete_object_at(pos),
        }
        action = editor_actions.get(self.editor_mode)
        if action:
            action()

    def _spawn_cargo_cycle(self, pos: Tuple[int, int]):
        # Rotate through cargo types for placement
        types = [CargoType.SMALL, CargoType.MEDIUM, CargoType.LARGE]
        if not hasattr(self, "_cargo_spawn_index"):
            self._cargo_spawn_index = 0
        cargo_type = types[self._cargo_spawn_index % len(types)]
        self._cargo_spawn_index += 1
        self.objects.append(GameObject(pos[0], pos[1], cargo_type))

    def _delete_object_at(self, pos: Tuple[int, int]):
        for collection, check in [
            (self.obstacles, lambda o: o.rect.collidepoint(pos)),
            (self.charging_stations, lambda s: s.rect.collidepoint(pos)),
            (self.workshops, lambda w: w.rect.collidepoint(pos)),
            (self.objects, lambda o: math.dist((o.pos.x, o.pos.y), pos) < 15),
        ]:
            for obj in collection[:]:
                if check(obj):
                    collection.remove(obj)
                    return

    def _handle_drone_selection(self, pos: Tuple[int, int]):
        clicked = next((d for d in self.drones if math.dist(d.pos.as_tuple(), pos) < d.size + 5), None)
        if clicked:
            keys = pygame.key.get_pressed()
            if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
                if clicked in self.selected_drones:
                    self.selected_drones.remove(clicked)
                    clicked.selected = False
                else:
                    self.selected_drones.append(clicked)
                    clicked.selected = True
            else:
                for d in self.selected_drones:
                    d.selected = False
                self.selected_drones = [clicked]
                clicked.selected = True
        else:
            self.drag_start = pos
            for d in self.selected_drones:
                d.selected = False
            self.selected_drones = []

    def _handle_drag_release(self, pos: Tuple[int, int]):
        if self.drag_rect:
            for drone in self.drones:
                if self.drag_rect.collidepoint(int(drone.pos.x), int(drone.pos.y)):
                    drone.selected = True
                    if drone not in self.selected_drones:
                        self.selected_drones.append(drone)
        self.drag_start = None
        self.drag_rect = None

    def _handle_context_menu_click(self, pos: Tuple[int, int]):
        menu_rect = pygame.Rect(
            self.ui.context_menu_pos[0],
            self.ui.context_menu_pos[1],
            config.CONTEXT_MENU_WIDTH,
            len(self.ui.context_menu_items) * config.CONTEXT_MENU_ITEM_HEIGHT,
        )
        if not menu_rect.collidepoint(pos):
            self.ui.context_menu_open = False
            return
        item_index = (pos[1] - menu_rect.y) // config.CONTEXT_MENU_ITEM_HEIGHT
        if 0 <= item_index < len(self.ui.context_menu_items):
            cmd_type = self.ui.context_menu_items[item_index][1]
            target_pos = tuple(self.ui.context_menu_pos)
            target_object = None
            if cmd_type == CommandType.PICK_UP:
                target_object = next(
                    (
                        o
                        for o in self.objects
                        if not o.picked_up and math.dist((o.pos.x, o.pos.y), target_pos) < 30
                    ),
                    None,
                )
            cmd = Command(cmd_type, target_pos, target_object)
            if self.selected_drones:
                processed_cargo_ids = set()
                for drone in self.selected_drones:
                    if drone == self.coordinator:
                        continue
                    cargo = getattr(drone, "carrying", None)
                    if cargo is None:
                        cargo = next((o for o in self.objects if hasattr(o, "carriers") and drone in o.carriers), None)
                    if cargo is not None:
                        cid = id(cargo)
                        if cid in processed_cargo_ids:
                            continue
                        processed_cargo_ids.add(cid)
                        for c in list(getattr(cargo, "carriers", [])):
                            if c != self.coordinator:
                                c.current_command = cmd
                                c.state = DroneState.CARRYING
                    else:
                        drone.current_command = cmd
                        drone.state = DroneState.MOVING
            else:
                self.pending_tasks.append(cmd)
        self.ui.context_menu_open = False

    def _handle_keyboard(self, key: int, mouse_pos: Tuple[int, int]):
        if key == pygame.K_ESCAPE:
            for drone in self.selected_drones:
                drone.selected = False
            self.selected_drones = []
            self.ui.context_menu_open = False
            self.ui.editor_menu_open = False
            self.editor_mode = EditorMode.NONE
        elif key == pygame.K_e:
            self.ui.editor_menu_open = not self.ui.editor_menu_open
            if not self.ui.editor_menu_open:
                self.editor_mode = EditorMode.NONE
        elif key == pygame.K_SPACE and self.selected_drones:
            cmd = Command(CommandType.FORMATION, mouse_pos)
            cmd.group_size = len(self.selected_drones)
            for drone in self.selected_drones:
                if drone != self.coordinator:
                    drone.current_command = cmd
                    drone.state = DroneState.MOVING
        elif key == pygame.K_p:
            self.paused = not self.paused

    def update(self, dt: float):
        self.sim_time += dt
        self._remove_dead_drones()
        if self.coordinator:
            self.coordinator.analyze_and_delegate(self.drones, self.pending_tasks, self.charging_stations, self.workshops)
        for drone in self.drones:
            drone.update(dt, self.drones, self.obstacles)
            if drone.carrying and getattr(drone.carrying, "picked_up", False):
                cargo = drone.carrying
                carriers = cargo.carriers if hasattr(cargo, "carriers") else [drone]
                if carriers:
                    avg = Vector2D(0, 0)
                    for c in carriers:
                        avg = avg + c.pos
                    cargo.pos = avg / len(carriers)
                    target_pos = None
                    for c in carriers:
                        if c.current_command and c.current_command.cmd_type == CommandType.MOVE_TO and c.current_command.target_pos:
                            target_pos = Vector2D(*c.current_command.target_pos)
                            break
                    try:
                        from metrics import mark_transport_started

                        if id(cargo) not in self._picked_objects_seen:
                            import time

                            self._picked_objects_seen.add(id(cargo))
                            mark_transport_started(time.time())
                    except Exception:
                        pass

                    if hasattr(cargo, "destination_pos") and (target_pos is None):
                        if not getattr(cargo, "was_dropped", False):
                            for c in carriers:
                                if c.current_command is None:
                                    c.current_command = Command(CommandType.MOVE_TO, (int(cargo.destination_pos.x), int(cargo.destination_pos.y)))
                                    c.state = DroneState.CARRYING

                    any_arrived = any(c.current_command is None for c in carriers)
                    if not any_arrived and target_pos is not None:
                        any_arrived = any(c.pos.distance_to(target_pos) <= config.PICKUP_DIST for c in carriers)

                    delivered_here = False
                    arrival_drone = None
                    if hasattr(cargo, "destination_pos"):
                            extra_tol = 0
                            try:
                                from entities.objects import CargoType

                                if getattr(cargo, "cargo_type", None) == CargoType.MEDIUM:
                                    extra_tol = config.GRID_CELL_SIZE // 2
                                elif getattr(cargo, "cargo_type", None) == CargoType.LARGE:
                                    extra_tol = config.GRID_CELL_SIZE
                            except Exception:
                                extra_tol = 0

                            tol = config.PICKUP_DIST + extra_tol

                            for c in carriers:
                                if c.pos.distance_to(cargo.destination_pos) <= config.PICKUP_DIST:
                                    arrival_drone = c
                                    delivered_here = True
                                    break

                            if not delivered_here:
                                if all(c.pos.distance_to(cargo.destination_pos) <= tol for c in carriers):
                                    delivered_here = True
                                else:
                                    idle_vel_thresh = 0.5
                                    fallback_dist = max(tol, config.GRID_CELL_SIZE)
                                    if all(c.velocity.length() < idle_vel_thresh and c.pos.distance_to(cargo.destination_pos) <= fallback_dist for c in carriers):
                                        delivered_here = True

                    if any_arrived:
                        for c in carriers:
                            c.current_command = None
                            c.path = []
                            c.path_index = 0
                            c.velocity = Vector2D(0, 0)
                            c.acceleration = Vector2D(0, 0)
                            c.state = DroneState.CARRYING

                    if delivered_here and not getattr(cargo, "delivered", False):
                        if arrival_drone is None:
                            arrive_candidates = [
                                c for c in carriers if c.current_command is None and c.pos.distance_to(cargo.destination_pos) <= max(tol, config.GRID_CELL_SIZE)
                            ]
                            if not arrive_candidates:
                                arrive_candidates = sorted(carriers, key=lambda c: c.pos.distance_to(cargo.destination_pos))
                            arrival_drone = arrive_candidates[0]

                        cargo.pos = Vector2D(arrival_drone.pos.x, arrival_drone.pos.y)
                        cargo.picked_up = False
                        cargo.delivered = True
                        try:
                            from metrics import mark_transport_completed

                            import time

                            mark_transport_completed(time.time())
                        except Exception:
                            pass

                        for c in list(carriers):
                            c.carrying = None
                            c.state = DroneState.IDLE
                            c.current_command = None
                            c.velocity = Vector2D(0, 0)
                            c.acceleration = Vector2D(0, 0)
                        cargo.carriers.clear()

            for obj in self.objects:
                if not hasattr(obj, "carriers"):
                    continue
                original_carriers = list(obj.carriers)
                valid_carriers = [c for c in original_carriers if getattr(c, "alive", True) and c.carrying is obj and c.state in (DroneState.EXECUTING, DroneState.CARRYING)]
                if len(valid_carriers) != len(original_carriers):
                    removed = [c for c in original_carriers if c not in valid_carriers]
                    for c in removed:
                        if getattr(c, "carrying", None) is obj:
                            c.carrying = None
                    obj.carriers = valid_carriers

                if getattr(obj, "picked_up", False) and len(obj.carriers) < obj.required_carriers:
                    if obj.carriers:
                        avg = Vector2D(0, 0)
                        for c in obj.carriers:
                            avg = avg + c.pos
                        obj.pos = avg / len(obj.carriers)
                    for c in list(obj.carriers):
                        c.carrying = None
                        c.state = DroneState.IDLE
                        c.current_command = None
                        c.velocity = Vector2D(0, 0)
                        c.acceleration = Vector2D(0, 0)
                    obj.carriers.clear()
                    obj.picked_up = False
                    obj.was_dropped = True

                if (
                    not getattr(obj, "picked_up", False)
                    and len(obj.carriers) < obj.required_carriers
                    and not getattr(obj, "delivered", False)
                    and not getattr(self, "unload_zone_rect", None)
                    or (
                        not getattr(obj, "picked_up", False)
                        and len(obj.carriers) < obj.required_carriers
                        and not getattr(obj, "delivered", False)
                        and self.unload_zone_rect is not None
                        and not self.unload_zone_rect.collidepoint(int(obj.pos.x), int(obj.pos.y))
                    )
                ):
                    already_pending = any(
                        t.cmd_type == CommandType.PICK_UP and t.target_object is obj for t in self.pending_tasks
                    )
                    assigned = any(
                        (d.current_command is not None and d.current_command.cmd_type == CommandType.PICK_UP and d.current_command.target_object is obj)
                        for d in self.drones
                    )
                    if not already_pending and not assigned:
                        self.pending_tasks.append(Command(CommandType.PICK_UP, (int(obj.pos.x), int(obj.pos.y)), obj))
        self._process_facilities(dt)

        try:
            from metrics import get_metrics

            m = get_metrics()
            if m.get("transport_tasks_total", 0) > 0 and m.get("transport_tasks_completed", 0) >= m.get("transport_tasks_total", 0):
                self.paused = True
        except Exception:
            pass

    def _remove_dead_drones(self):
        dead = [d for d in self.drones if not getattr(d, "alive", True)]
        if not dead:
            return
        for d in dead:
            if d in self.selected_drones:
                self.selected_drones.remove(d)
            if d is self.coordinator:
                self.coordinator = None
            self.drones.remove(d)

    def _process_facilities(self, dt: float):
        for station in self.charging_stations:
            self._process_facility(station, dt, DroneState.RECHARGING, "energy", "max_energy")
        for workshop in self.workshops:
            self._process_facility(workshop, dt, DroneState.REPAIRING, "hp", "max_hp")

    def _process_facility(self, facility, dt: float, state: DroneState, attr: str, max_attr: str):
        inside = [
            d
            for d in self.drones
            if facility.rect.collidepoint(int(d.pos.x), int(d.pos.y)) and d.state == state
        ]
        if not inside:
            return
        inside.sort(key=lambda d: getattr(d, attr))
        for drone in inside[:2]:
            facility.process_drone(drone, dt, attr, max_attr)

    def draw(self):
        self.screen.fill(config.WHITE)
        for x in range(0, config.SCREEN_WIDTH, config.GRID_CELL_SIZE):
            pygame.draw.line(self.screen, config.GRID_COLOR, (x, 0), (x, config.SCREEN_HEIGHT), 1)
        for y in range(0, config.SCREEN_HEIGHT, config.GRID_CELL_SIZE):
            pygame.draw.line(self.screen, config.GRID_COLOR, (0, y), (config.SCREEN_WIDTH, y), 1)


        try:
            import pygame as _pg
            _pg.draw.rect(self.screen, (180, 220, 255), self.load_zone_rect)
            _pg.draw.rect(self.screen, (255, 220, 180), self.unload_zone_rect)
            font = pygame.font.Font(None, 20)
            self.screen.blit(font.render("LOAD", True, config.BLACK), (self.load_zone_rect.x + 6, self.load_zone_rect.y - 16))
            self.screen.blit(font.render("UNLOAD", True, config.BLACK), (self.unload_zone_rect.x + 6, self.unload_zone_rect.y - 16))
        except Exception:
            pass

        for obj in self.obstacles + self.charging_stations + self.workshops:
            obj.draw(self.screen)
        for obj in [o for o in self.objects if not getattr(o, "picked_up", False)]:
            obj.draw(self.screen)

        # drones
        for drone in self.drones:
            drone.draw(self.screen)

        for obj in [o for o in self.objects if getattr(o, "picked_up", False)]:
            obj.draw(self.screen)

        if self.drag_rect:
            pygame.draw.rect(self.screen, config.GREEN, self.drag_rect, 2)
        self.ui.draw_info_panel(self.screen, self.selected_drones)
        self.ui.draw_coordinator_status(self.screen, len(self.pending_tasks))
        self.ui.draw_context_menu(self.screen)
        self.ui.draw_editor_menu(self.screen)
        self.ui.draw_help(self.screen)

        try:
            from metrics import get_metrics

            m = get_metrics()
            font = pygame.font.Font(None, 20)
            x = 10
            y = 10
            try:
                import time

                t_start = m.get("transport_start_time")
                t_end = m.get("transport_end_time")
                if t_start is None:
                    transport_time_str = "-"
                else:
                    if t_end is None:
                        transport_time = time.time() - t_start
                    else:
                        transport_time = t_end - t_start
                    transport_time_str = f"{transport_time:.1f} s"
            except Exception:
                transport_time_str = "-"

            lines = [
                f"Total distance: {m['total_distance'] / max(1, config.GRID_CELL_SIZE):.1f} m",
                f"Collisions: {m['collision_count']}",
                f"Dead drones: {m['dead_drones']}",
                f"Transport tasks: {m['transport_tasks_completed']}/{m['transport_tasks_total']}",
                f"Transport time: {transport_time_str}",
            ]
            for i, line in enumerate(lines):
                self.screen.blit(font.render(line, True, config.BLACK), (x, y + i * 18))
        except Exception:
            pass

        if self.editor_mode != EditorMode.NONE:
            font = pygame.font.Font(None, 36)
            text = font.render(f"EDITOR: {self.editor_mode.name}", True, config.YELLOW)
            self.screen.blit(text, (config.SCREEN_WIDTH // 2 - 150, 10))
        pygame.display.flip()

    def run(self):
        while self.running:
            dt = self.clock.tick(config.FPS) / 1000.0
            self.handle_events()
            if not getattr(self, "paused", False):
                self.update(dt)
            self.draw()
        pygame.quit()

