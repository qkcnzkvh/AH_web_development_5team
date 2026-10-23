import enum

class Gender(str, enum.Enum):
    M = "M"
    F = "F"

class Role(str, enum.Enum):
    PENDING = "PENDING"
    STAFF = "STAFF"
    ADMIN = "ADMIN"

class Department(str, enum.Enum):
    MEDICAL = "MEDICAL"
    DEV = "DEV"
    RESEARCH = "RESEARCH"