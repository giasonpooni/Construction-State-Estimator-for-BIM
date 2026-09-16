"""SE(2) as the configuration space for planar pose.

Poses are (x, y, theta) with theta in (-pi, pi]. Incremental motion and
process noise live in the Lie algebra se(2) and are composed on the left
of the body frame (odometry convention). This is a group morphism, not
R^3 addition.
"""

from __future__ import annotations

import math

import numpy as np

_EPS = 1e-12


def wrap_angle(theta: np.ndarray | float) -> np.ndarray | float:
    """Map angle to (-pi, pi]."""
    return (theta + math.pi) % (2.0 * math.pi) - math.pi


def rotate(theta: float, vec: np.ndarray) -> np.ndarray:
    c, s = math.cos(theta), math.sin(theta)
    x, y = float(vec[0]), float(vec[1])
    return np.array([c * x - s * y, s * x + c * y], dtype=np.float64)


def compose(pose: np.ndarray, body: np.ndarray) -> np.ndarray:
    """pose ⊕ body, body expressed in the current body frame."""
    x, y, th = float(pose[0]), float(pose[1]), float(pose[2])
    dx, dy, dth = float(body[0]), float(body[1]), float(body[2])
    c, s = math.cos(th), math.sin(th)
    return np.array(
        [x + c * dx - s * dy, y + s * dx + c * dy, float(wrap_angle(th + dth))],
        dtype=np.float64,
    )


def inverse(pose: np.ndarray) -> np.ndarray:
    x, y, th = float(pose[0]), float(pose[1]), float(pose[2])
    c, s = math.cos(th), math.sin(th)
    return np.array(
        [-c * x - s * y, s * x - c * y, float(wrap_angle(-th))],
        dtype=np.float64,
    )


def relative(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Body-frame increment taking a to b: a^{-1} ⊕ b."""
    return compose(inverse(a), b)


def exp_se2(xi: np.ndarray) -> np.ndarray:
    """Exponential map se(2) -> SE(2) as a body increment (x, y, theta)."""
    vx, vy, w = float(xi[0]), float(xi[1]), float(xi[2])
    if abs(w) < _EPS:
        return np.array([vx, vy, 0.0], dtype=np.float64)
    a = math.sin(w) / w
    b = (1.0 - math.cos(w)) / w
    return np.array([a * vx - b * vy, b * vx + a * vy, w], dtype=np.float64)


def unicycle_increment(v: float, omega: float, dt: float) -> np.ndarray:
    """Exact integration of body twist (v, 0, omega) over dt."""
    return exp_se2(np.array([v * dt, 0.0, omega * dt], dtype=np.float64))


def adjoint(pose: np.ndarray) -> np.ndarray:
    """Ad_T on se(2) coordinates (vx, vy, omega)."""
    x, y, th = float(pose[0]), float(pose[1]), float(pose[2])
    c, s = math.cos(th), math.sin(th)
    return np.array(
        [[c, -s, y], [s, c, -x], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )


def transport_tangent(increment: np.ndarray, tangent: np.ndarray) -> np.ndarray:
    """Push a tangent vector through a body increment (discrete Jacobi)."""
    return adjoint(increment) @ np.asarray(tangent, dtype=np.float64)


def circular_mean_angle(angles: np.ndarray, weights: np.ndarray) -> float:
    s = float(np.sum(weights * np.sin(angles)))
    c = float(np.sum(weights * np.cos(angles)))
    return float(math.atan2(s, c))


def weighted_mean_pose(poses: np.ndarray, weights: np.ndarray) -> np.ndarray:
    w = np.asarray(weights, dtype=np.float64)
    p = np.asarray(poses, dtype=np.float64)
    return np.array(
        [
            float(np.sum(w * p[:, 0])),
            float(np.sum(w * p[:, 1])),
            circular_mean_angle(p[:, 2], w),
        ],
        dtype=np.float64,
    )


def tangent_covariance(poses: np.ndarray, weights: np.ndarray, mean: np.ndarray) -> np.ndarray:
    """Weighted covariance of body-frame increments from the mean pose."""
    w = np.asarray(weights, dtype=np.float64)
    xi = np.stack([relative(mean, pose) for pose in poses])
    return (xi.T * w) @ xi
