from copy import deepcopy
from typing import Any


def row_matches_key(row: Any, key_field: str, key_value: Any) -> bool:
    if not isinstance(row, dict):
        return False

    return str(row.get(key_field)) == str(key_value)


class InMemoryResourceStore:
    def __init__(self) -> None:
        self._resources: dict[str, list[dict[str, Any]]] = {}

    def seed(self, resource_name: str, rows: list[dict[str, Any]]) -> None:
        if resource_name not in self._resources:
            self._resources[resource_name] = deepcopy(rows)

    def list(self, resource_name: str) -> list[dict[str, Any]]:
        return deepcopy(self._resources.get(resource_name, []))

    def get_by_key(
        self,
        resource_name: str,
        key_field: str,
        key_value: Any,
    ) -> dict[str, Any] | None:
        rows = self._resources.get(resource_name, [])
        for row in rows:
            if row_matches_key(row, key_field, key_value):
                return deepcopy(row)
        return None

    def create(
        self,
        resource_name: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if resource_name not in self._resources:
            self._resources[resource_name] = []

        stored_payload = deepcopy(payload)
        self._resources[resource_name].append(stored_payload)
        return deepcopy(stored_payload)

    def update(
        self,
        resource_name: str,
        key_field: str,
        key_value: Any,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        rows = self._resources.get(resource_name, [])

        for index, row in enumerate(rows):
            if row_matches_key(row, key_field, key_value):
                updated = deepcopy(row)
                updated.update(payload)
                rows[index] = updated
                return deepcopy(updated)

        return None

    def delete(
        self,
        resource_name: str,
        key_field: str,
        key_value: Any,
    ) -> bool:
        rows = self._resources.get(resource_name, [])

        for index, row in enumerate(rows):
            if row_matches_key(row, key_field, key_value):
                del rows[index]
                return True

        return False
