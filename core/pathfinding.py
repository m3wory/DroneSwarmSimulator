import heapq
from typing import List, Tuple, Optional

import config
from core.vector import Vector2D


class AStarPathfinder:
    def __init__(self, grid_size: Optional[int] = None):
        self.grid_size = grid_size or config.A_STAR_GRID_SIZE
        self.grid_width = config.SCREEN_WIDTH // self.grid_size
        self.grid_height = config.SCREEN_HEIGHT // self.grid_size

    def world_to_grid(self, pos: Vector2D):
        return int(pos.x // self.grid_size), int(pos.y // self.grid_size)

    def grid_to_world(self, grid_pos: Tuple[int, int]):
        return Vector2D(
            grid_pos[0] * self.grid_size + self.grid_size // 2,
            grid_pos[1] * self.grid_size + self.grid_size // 2,
        )

    def heuristic(self, a: Tuple[int, int], b: Tuple[int, int]):
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def get_neighbors(self, pos: Tuple[int, int]):
        steps = [(0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)]
        return [
            (pos[0] + dx, pos[1] + dy)
            for dx, dy in steps
            if 0 <= pos[0] + dx < self.grid_width and 0 <= pos[1] + dy < self.grid_height
        ]

    def _blocked_cells(self, obstacles):
        blocked = set()
        for obstacle in obstacles:
            if hasattr(obstacle, "rect"):
                for x in range(obstacle.rect.left // self.grid_size, (obstacle.rect.right // self.grid_size) + 1):
                    for y in range(obstacle.rect.top // self.grid_size, (obstacle.rect.bottom // self.grid_size) + 1):
                        if 0 <= x < self.grid_width and 0 <= y < self.grid_height:
                            blocked.add((x, y))
        return blocked

    def find_path(self, start: Vector2D, goal: Vector2D, obstacles: List):
        start_grid, goal_grid = self.world_to_grid(start), self.world_to_grid(goal)
        blocked = self._blocked_cells(obstacles)

        open_set = [(0, start_grid)]
        came_from = {}
        g_score = {start_grid: 0}
        f_score = {start_grid: self.heuristic(start_grid, goal_grid)}

        while open_set:
            current = heapq.heappop(open_set)[1]
            if current == goal_grid:
                path = []
                while current in came_from:
                    path.append(self.grid_to_world(current))
                    current = came_from[current]
                return path[::-1]

            for neighbor in self.get_neighbors(current):
                if neighbor in blocked:
                    continue
                tentative_g = g_score[current] + 1
                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score[neighbor] = tentative_g + self.heuristic(neighbor, goal_grid)
                    heapq.heappush(open_set, (f_score[neighbor], neighbor))
        return []

