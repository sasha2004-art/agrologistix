from enum import StrEnum


class AuthRole(StrEnum):
    DISPATCHER = "dispatcher"
    ADMIN = "admin"


class RoadType(StrEnum):
    ASPHALT = "asphalt"
    DIRT = "dirt"


class DeliveryStatus(StrEnum):
    """Этапы поставки заявки.

    ``PENDING`` — «В плане»: заявка ожидает, её спрос участвует в расчёте.
    ``IN_PROGRESS`` — «В работе»: груз отгружен по последнему плану (сток списан),
    заявка исключена из нового расчёта, но получение ещё не подтверждено.
    ``DELIVERED`` — «Доставлено»: заявка закрыта.
    """

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DELIVERED = "delivered"


class TruckStatus(StrEnum):
    ACTIVE = "active"
    BROKEN = "broken"


class StopStatus(StrEnum):
    PLANNED = "planned"
    DELIVERED = "delivered"


class WeatherMode(StrEnum):
    NORMAL = "normal"
    HEATWAVE_35C = "heatwave_35c"
    HEAVY_RAIN = "heavy_rain"


class WarningSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
