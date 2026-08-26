from copy import deepcopy
from pathlib import Path
from typing import Any

from mockyfast.persistence import write_state


def row_matches_key(row: Any, key_field: str, key_value: Any) -> bool:
    if not isinstance(row, dict):
        return False

    return str(row.get(key_field)) == str(key_value)


class InMemoryResourceStore:
    def __init__(self) -> None:
        self._resources: dict[str, list[dict[str, Any]]] = {}
        self._state_paths: dict[str, Path] = {}

    def has(self, resource_name: str) -> bool:
        return resource_name in self._resources

    def persist_to(self, resource_name: str, state_path: Path) -> None:
        self._state_paths[resource_name] = state_path

    def flush(self, resource_name: str) -> None:
        state_path = self._state_paths.get(resource_name)

        if state_path is not None:
            write_state(state_path, self._resources.get(resource_name, []))

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
        self.flush(resource_name)

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
                self.flush(resource_name)

                return deepcopy(updated)

        return None

    def replace(
        self,
        resource_name: str,
        key_field: str,
        key_value: Any,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Swap the whole resource for the payload, keeping its key field."""
        rows = self._resources.get(resource_name, [])

        for index, row in enumerate(rows):
            if row_matches_key(row, key_field, key_value):
                replacement = deepcopy(payload)
                replacement[key_field] = row[key_field]
                rows[index] = replacement
                self.flush(resource_name)

                return deepcopy(replacement)

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
                self.flush(resource_name)

                return True

        return False
