from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class SystemMetrics:
    total_ram_gb: float
    used_ram_gb: float
    total_storage_gb: float
    used_storage_gb: float
    collected_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class PackageEntry:
    name: str
    source: str
    installed_version: str
    latest_version: str
    status: str
    update_available: bool
    can_toggle: bool
    enabled: bool


@dataclass(slots=True)
class BluetoothDeviceEntry:
    address: str
    name: str
    connected: bool
    battery_percent: str


@dataclass(slots=True)
class PartitionEntry:
    device: str
    filesystem: str
    mountpoint: str
    size: str
    status: str
