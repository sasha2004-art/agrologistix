from enum import StrEnum


class AuthRole(StrEnum):
    DISPATCHER = "dispatcher"
    ADMIN = "admin"


class RoadType(StrEnum):
    ASPHALT = "asphalt"
    DIRT = "dirt"


class DeliveryStatus(StrEnum):
    PENDING = "pending"
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
