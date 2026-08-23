"""Project scanner core (framework-neutral, no Click).

PROJECT-0001 introduces only the file-inventory primitive. Graph persistence
and GDScript/TSCN parsing arrive in later slices.
"""

from .inventory import inventory_project
from .model import InventoryResult

__all__ = ["inventory_project", "InventoryResult"]
