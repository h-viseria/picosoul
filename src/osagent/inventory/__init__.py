"""Persistent system inventory: apps, devices, defaults, control hints."""

from __future__ import annotations

from osagent.inventory.service import InventoryService, get_inventory

__all__ = ["InventoryService", "get_inventory"]
