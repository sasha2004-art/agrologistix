"""Stop ordering: nearest neighbour plus a direction-safe 2-opt pass."""

from app.services.solver_routing import nearest_neighbour_order, two_opt_order

# A directional distance matrix (rows = from, columns = to) where the classic
# two-edge delta would accept a reversal that makes the whole route longer.
# Index 0 is the depot; 1..4 are delivery points.
DIRECTIONAL_COSTS = (
    (0.0, 27.0, 15.0, 30.0, 26.0),
    (6.0, 0.0, 21.0, 28.0, 11.0),
    (24.0, 20.0, 0.0, 6.0, 46.0),
    (33.0, 50.0, 14.0, 0.0, 9.0),
    (50.0, 45.0, 38.0, 17.0, 0.0),
)


def _index(point: tuple[float, float]) -> int:
    return int(point[0])


def _directional_distance(costs: tuple[tuple[float, ...], ...]):
    def distance(origin: tuple[float, float], destination: tuple[float, float]) -> float:
        return costs[_index(origin)][_index(destination)]

    return distance


def _route_length(route, points, origin, distance) -> float:
    total = 0.0
    current = origin
    for position in route:
        total += distance(current, points[position])
        current = points[position]
    return total


def test_two_opt_never_makes_a_directional_route_longer() -> None:
    origin = (0.0, 0.0)
    points = [(float(index), 0.0) for index in range(1, 5)]
    distance = _directional_distance(DIRECTIONAL_COSTS)

    initial = nearest_neighbour_order(origin, points, distance)
    improved = two_opt_order(origin, points, initial, distance)

    initial_length = _route_length(initial, points, origin, distance)
    improved_length = _route_length(improved, points, origin, distance)
    assert improved_length <= initial_length + 1e-9


def test_two_opt_shortens_a_symmetric_route() -> None:
    origin = (0.0, 0.0)
    # Points are visited in a deliberately crossing order: 1, 3, 2, 4.
    points = [(1.0, 0.0), (2.0, 0.1), (3.0, 0.0), (4.0, 0.1)]

    def distance(first: tuple[float, float], second: tuple[float, float]) -> float:
        return abs(first[0] - second[0]) + abs(first[1] - second[1])

    initial = [0, 2, 1, 3]
    improved = two_opt_order(origin, points, initial, distance)

    assert _route_length(improved, points, origin, distance) < _route_length(
        initial, points, origin, distance
    )
