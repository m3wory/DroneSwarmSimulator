import time

metrics = {
    "total_distance": 0.0,
    "collision_count": 0,
    "dead_drones": 0,
    "transport_tasks_total": 0,
    "transport_tasks_completed": 0,
    "transport_start_time": None,
    "transport_end_time": None,
}


def add_distance(d):
    metrics["total_distance"] += float(d)


def increment_collision():
    metrics["collision_count"] += 1


def increment_dead():
    metrics["dead_drones"] += 1


def set_transport_total(n):
    metrics["transport_tasks_total"] = int(n)


def mark_transport_started(now=None):
    if metrics["transport_start_time"] is None:
        metrics["transport_start_time"] = now if now is not None else time.time()


def mark_transport_completed(now=None):
    metrics["transport_tasks_completed"] += 1
    if metrics["transport_tasks_completed"] >= metrics["transport_tasks_total"]:
        metrics["transport_end_time"] = now if now is not None else time.time()


def get_metrics():
    return metrics.copy()
