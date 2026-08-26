from pathlib import Path


def resolve_data_path(config_path: str, relative_path: str, kind: str) -> Path:
    """
    Resolve a file referenced by the configuration, keeping it inside the
    configuration directory.
    """
    base_path = Path(config_path).parent.resolve()
    resolved_path = (base_path / relative_path).resolve()

    if not resolved_path.is_relative_to(base_path):
        raise ValueError(
            f"{kind} file must stay inside the configuration directory: {relative_path}"
        )

    if not resolved_path.exists():
        raise FileNotFoundError(f"{kind} file not found: {relative_path}")

    return resolved_path


def resolve_writable_path(config_path: str, relative_path: str, kind: str) -> Path:
    """Same confinement as resolve_data_path, for a file that need not exist yet."""
    base_path = Path(config_path).parent.resolve()
    resolved_path = (base_path / relative_path).resolve()

    if not resolved_path.is_relative_to(base_path):
        raise ValueError(
            f"{kind} file must stay inside the configuration directory: {relative_path}"
        )

    return resolved_path
