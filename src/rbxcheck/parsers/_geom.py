"""Petits utilitaires géométriques partagés."""

from __future__ import annotations

Vec3 = tuple[float, float, float]


class BBox:
    """Boîte englobante qui se remplit au fil des points."""

    def __init__(self) -> None:
        self.min: list[float] | None = None
        self.max: list[float] | None = None

    def add(self, p: Vec3) -> None:
        if self.min is None or self.max is None:
            self.min = list(p)
            self.max = list(p)
            return
        for i in range(3):
            if p[i] < self.min[i]:
                self.min[i] = p[i]
            if p[i] > self.max[i]:
                self.max[i] = p[i]

    def as_tuples(self) -> tuple[Vec3 | None, Vec3 | None]:
        if self.min is None or self.max is None:
            return None, None
        return (
            (self.min[0], self.min[1], self.min[2]),
            (self.max[0], self.max[1], self.max[2]),
        )


def is_degenerate(a: Vec3, b: Vec3, c: Vec3, eps: float = 1e-12) -> bool:
    """Vrai si le triangle a une aire (quasi) nulle."""
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    cx = uy * vz - uz * vy
    cy = uz * vx - ux * vz
    cz = ux * vy - uy * vx
    return (cx * cx + cy * cy + cz * cz) <= eps * eps
