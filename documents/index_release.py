from __future__ import annotations

from dataclasses import dataclass


class IndexReleaseError(ValueError):
    """Raised when an index alias transition is unsafe."""


@dataclass(frozen=True)
class AliasSwitchPlan:
    alias: str
    current_collection: str | None
    target_collection: str

    def __post_init__(self) -> None:
        if not self.alias.strip() or not self.target_collection.strip():
            raise IndexReleaseError("alias and target_collection must not be empty")
        if self.current_collection == self.target_collection:
            raise IndexReleaseError("target collection must differ from the current collection")

    def rollback(self) -> "AliasSwitchPlan":
        if not self.current_collection:
            raise IndexReleaseError("cannot roll back an alias that had no previous collection")
        return AliasSwitchPlan(
            alias=self.alias,
            current_collection=self.target_collection,
            target_collection=self.current_collection,
        )
