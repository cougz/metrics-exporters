"""Proxmox-specific collectors"""
from .system import ProxmoxSystemCollector
from .containers import ContainerInventoryCollector

__all__ = [
    'ProxmoxSystemCollector',
    'ContainerInventoryCollector'
]