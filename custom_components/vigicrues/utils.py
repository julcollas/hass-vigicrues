"""Utility functions for Vigicrues integration."""
import math


def lambert93_to_wgs84(x: float, y: float) -> tuple[float, float]:
    """Convert Lambert 93 coordinates (x, y) to WGS84 (latitude, longitude).

    Parameters:
        x: The X-coordinate in Lambert 93 (meters).
        y: The Y-coordinate in Lambert 93 (meters).

    Returns:
        tuple: (latitude, longitude) in WGS84 (degrees).
    """
    # Constants for the Lambert 93 projection
    e = 0.0818191910428158  # Ellipsoid eccentricity
    n = 0.7256077650532670  # Projection scale factor
    c = 11754255.4261  # Projection constant
    Xs = 700000.0  # X-coordinate of the false origin
    Ys = 12655612.0499  # Y-coordinate of the false origin
    lambda0 = 3 * math.pi / 180  # Central meridian (3°E in radians)

    # Calculate the polar radius and angle
    r = math.sqrt((x - Xs) ** 2 + (y - Ys) ** 2)
    gamma = math.atan((x - Xs) / (Ys - y))

    # Compute the isometric latitude
    l = -math.log(abs(r / c)) / n

    # Iteratively compute the geographic latitude
    phi = 2 * math.atan(math.exp(l)) - math.pi / 2
    for _ in range(7):
        phi = (
            2
            * math.atan(
                ((1 + e * math.sin(phi)) / (1 - e * math.sin(phi))) ** (e / 2)
                * math.exp(l)
            )
            - math.pi / 2
        )

    # Compute the geographic longitude
    lon = lambda0 + gamma / n

    return math.degrees(phi), math.degrees(lon)
