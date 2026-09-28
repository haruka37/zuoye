"""Tool registry. Adding a new tool = one module here + one build_* function.

Phase 2 plan: add modules for the remaining Go endpoints (get_pet, create_pet,
update_pet, delete_pet, pet_records, pet_charges, stats, search, ...) and
register them in ``server.py`` — reuse ``PetHospitalClient``, the unified
error helpers and the JSON logging conventions unchanged.
"""

from .list_pets import (
    LIST_PETS_DESCRIPTION,
    ListPetsInput,
    PetItem,
    PetListData,
    build_list_pets_tool,
)

__all__ = [
    "LIST_PETS_DESCRIPTION",
    "ListPetsInput",
    "PetItem",
    "PetListData",
    "build_list_pets_tool",
]
