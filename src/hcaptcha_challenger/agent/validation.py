"""Validation for model-generated browser coordinates."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ViewportBounds:
    """The live browser-space bounds of a challenge viewport."""

    x: float
    y: float
    width: float
    height: float

    @property
    def x_end(self) -> float:
        return self.x + self.width

    @property
    def y_end(self) -> float:
        return self.y + self.height

    def contains(self, x: float, y: float) -> bool:
        return self.x <= x <= self.x_end and self.y <= y <= self.y_end


@dataclass(frozen=True)
class CoordinateViolation:
    """A model-generated coordinate outside the live viewport."""

    role: str
    x: float
    y: float
    bounds: ViewportBounds

    def as_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "x": self.x,
            "y": self.y,
            "bounds": asdict(self.bounds),
        }


class BoundsValidationError(Exception):
    """Raised before browser input when one or more coordinates are invalid."""

    def __init__(self, violations: list[CoordinateViolation]):
        self.violations = violations
        detail = "; ".join(
            f"{item.role}=({item.x},{item.y}) outside "
            f"x={item.bounds.x}..{item.bounds.x_end}, "
            f"y={item.bounds.y}..{item.bounds.y_end}"
            for item in violations
        )
        super().__init__(f"Browser coordinate rejected before input: {detail}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "message": str(self),
            "violations": [item.as_dict() for item in self.violations],
        }


class CoordinateBoundsValidator:
    """Validate parsed point and path responses against browser-space bounds."""

    @staticmethod
    def validate_points(
        points: Iterable[Any], bounds: ViewportBounds
    ) -> list[CoordinateViolation]:
        return [
            CoordinateViolation("point", float(point.x), float(point.y), bounds)
            for point in points
            if not bounds.contains(float(point.x), float(point.y))
        ]

    @staticmethod
    def validate_paths(
        paths: Iterable[Any], bounds: ViewportBounds
    ) -> list[CoordinateViolation]:
        violations: list[CoordinateViolation] = []
        for path in paths:
            for role, point in (
                ("drag-start", path.start_point),
                ("drag-end", path.end_point),
            ):
                x, y = float(point.x), float(point.y)
                if not bounds.contains(x, y):
                    violations.append(CoordinateViolation(role, x, y, bounds))
        return violations

    @classmethod
    def require_points(cls, points: Iterable[Any], bounds: ViewportBounds) -> None:
        violations = cls.validate_points(points, bounds)
        if violations:
            raise BoundsValidationError(violations)

    @classmethod
    def require_paths(cls, paths: Iterable[Any], bounds: ViewportBounds) -> None:
        violations = cls.validate_paths(paths, bounds)
        if violations:
            raise BoundsValidationError(violations)


def validate_points(points: Iterable[Any], bounds: ViewportBounds) -> list[CoordinateViolation]:
    """Return all point-coordinate violations."""
    return CoordinateBoundsValidator.validate_points(points, bounds)


def validate_paths(paths: Iterable[Any], bounds: ViewportBounds) -> list[CoordinateViolation]:
    """Return all drag-path coordinate violations."""
    return CoordinateBoundsValidator.validate_paths(paths, bounds)
