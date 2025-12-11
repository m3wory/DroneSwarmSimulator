import math


class Vector2D:
    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y

    def __add__(self, other):
        return Vector2D(self.x + other.x, self.y + other.y)

    def __sub__(self, other):
        return Vector2D(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float):
        return Vector2D(self.x * scalar, self.y * scalar)

    def __truediv__(self, scalar: float):
        return Vector2D(self.x / scalar, self.y / scalar) if scalar else Vector2D(0, 0)

    def length(self):
        return math.sqrt(self.x**2 + self.y**2)

    def normalize(self):
        return self / self.length() if self.length() > 0 else Vector2D(0, 0)

    def limit(self, max_val: float):
        return self.normalize() * max_val if self.length() > max_val else self

    def distance_to(self, other):
        return math.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2)

    def as_tuple(self):
        return self.x, self.y
