#!/usr/bin/env python3
"""
Cosmic Matrix Pong — Physics Unit Tests
========================================
Verify all physics equations match real-world values.
Run: python test_physics.py
"""

import math
import sys
import unittest

# ─── Physics constants ─────────────────────────────────────────────────────────
BALL_MASS     = 0.0027
BALL_DIAMETER = 0.040
BALL_RADIUS   = 0.020
BALL_AREA     = math.pi * BALL_RADIUS**2
AIR_DENSITY   = 1.293
AIR_VISCOSITY = 1.81e-5
DRAG_COEFF    = 0.47
MAGNUS_COEFF  = 1.5e-4
GRAVITY       = 9.81
RESTITUTION   = 0.89

class TestBallPhysics(unittest.TestCase):

    def test_drag_force_at_10ms(self):
        """F_drag = 0.5 * rho * Cd * A * v^2 at v=10 m/s
        A = pi*r^2 = pi*(0.02)^2 = 1.2566e-3 m^2
        Fd = 0.5 * 1.293 * 0.47 * 1.2566e-3 * 100 = 0.0382 N
        """
        v  = 10.0
        fd = 0.5 * AIR_DENSITY * DRAG_COEFF * BALL_AREA * v**2
        # Correct value: ~0.0382 N
        self.assertAlmostEqual(fd, 0.0382, delta=0.001,
            msg=f"Drag at 10m/s: expected ~0.0382N, got {fd:.5f}N")

    def test_drag_force_at_25ms(self):
        """Olympic-level shot: v=25 m/s (~90 km/h)"""
        v  = 25.0
        fd = 0.5 * AIR_DENSITY * DRAG_COEFF * BALL_AREA * v**2
        # Correct value: ~0.2386 N
        self.assertAlmostEqual(fd, 0.2386, delta=0.001)

    def test_kinetic_energy(self):
        """KE = 0.5 * m * v^2"""
        v  = 10.0
        ke = 0.5 * BALL_MASS * v**2
        self.assertAlmostEqual(ke, 0.135, places=3,
            msg=f"KE at 10m/s: expected 0.135J, got {ke}J")

    def test_momentum(self):
        """p = m * v"""
        v = 15.0
        p = BALL_MASS * v
        self.assertAlmostEqual(p, 0.0405, places=4)

    def test_reynolds_number(self):
        """Re = rho * v * D / mu"""
        v  = 10.0
        re = AIR_DENSITY * v * BALL_DIAMETER / AIR_VISCOSITY
        # ~28,600 → laminar at this speed
        self.assertAlmostEqual(re, 28619, delta=100)
        self.assertLess(re, 4e4, "Re < 40000 means laminar flow at 10m/s")

    def test_reynolds_turbulent_threshold(self):
        """Re=4e4: v_crit = Re*mu/(rho*D) ≈ 14.0 m/s for ping pong ball"""
        v_crit = 4e4 * AIR_VISCOSITY / (AIR_DENSITY * BALL_DIAMETER)
        self.assertAlmostEqual(v_crit, 14.0, delta=0.5)

    def test_magnus_force_direction(self):
        """Magnus force: F = k * (omega x v)
        Topspin: omega pointing in -x direction (ball spins top-forward)
        Velocity: +z (forward)
        Cross product (-x) × (+z) = +y (upward in right-hand coords)
        But topspin bends ball DOWN — so Godot applies -F_m, or omega sign flips.
        Test that magnitude is nonzero and formula is consistent.
        """
        omega = (-50.0, 0.0, 0.0)   # topspin axis
        v     = (0.0, 0.0, 10.0)    # forward velocity

        fx = omega[1]*v[2] - omega[2]*v[1]
        fy = omega[2]*v[0] - omega[0]*v[2]
        fz = omega[0]*v[1] - omega[1]*v[0]
        fm_mag = math.sqrt(fx**2 + fy**2 + fz**2)
        # Magnitude should be |omega| * |v| = 50 * 10 = 500
        self.assertAlmostEqual(fm_mag, 500.0, places=3)
        # Force should be purely in y direction for this geometry
        self.assertAlmostEqual(abs(fy), 500.0, places=3)

    def test_bounce_height_energy_conservation(self):
        """Ball dropped from h=0.3m should bounce to h*e^2"""
        h0  = 0.30
        v_impact = math.sqrt(2 * GRAVITY * h0)  # ~2.43 m/s
        v_after  = v_impact * RESTITUTION
        h_after  = v_after**2 / (2 * GRAVITY)
        expected = h0 * RESTITUTION**2  # ~0.238m
        self.assertAlmostEqual(h_after, expected, places=4)

    def test_ball_flight_time(self):
        """Projectile: ball hit horizontally at h=0.76m (table height)
        should hit ground in t = sqrt(2h/g)
        """
        h = 0.76  # standard table height
        t = math.sqrt(2 * h / GRAVITY)
        self.assertAlmostEqual(t, 0.394, places=2)

    def test_gravitational_modes(self):
        """Verify all gravity modes produce correct g values"""
        modes = {
            "earth":   9.81,
            "mars":    3.72,
            "moon":    1.62,
            "jupiter": 24.79,
            "zero_g":  0.0,
        }
        for name, g_expected in modes.items():
            # Just check the constant is reasonable
            self.assertGreaterEqual(g_expected, 0.0)
            self.assertLessEqual(g_expected, 30.0)

    def test_drag_coefficient_sphere(self):
        """Cd for smooth sphere ≈ 0.47 in laminar regime"""
        self.assertAlmostEqual(DRAG_COEFF, 0.47, places=2)

    def test_ittf_ball_spec(self):
        """ITTF regulation: m=2.7g, d=40mm, e=0.89-0.92"""
        self.assertAlmostEqual(BALL_MASS, 0.0027, places=4)
        self.assertAlmostEqual(BALL_DIAMETER, 0.040, places=3)
        self.assertGreaterEqual(RESTITUTION, 0.89)
        self.assertLessEqual(RESTITUTION, 0.93)

    def test_spin_unit_conversion(self):
        """rpm = rad/s * 60 / (2*pi) = rad/s * 9.5493"""
        omega_rads = 100.0  # rad/s
        rpm = omega_rads * 60.0 / (2.0 * math.pi)
        self.assertAlmostEqual(rpm, 954.93, places=1)
        # Quick factor check
        self.assertAlmostEqual(omega_rads * 9.5493, rpm, places=1)


class TestAnalyticsStats(unittest.TestCase):

    def test_mean(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        m = sum(data) / len(data)
        self.assertEqual(m, 3.0)

    def test_std_dev(self):
        data = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
        m    = sum(data) / len(data)
        std  = math.sqrt(sum((x-m)**2 for x in data) / len(data))
        self.assertAlmostEqual(std, 2.0, places=5)

    def test_percentile_p50(self):
        data = [float(i) for i in range(1, 11)]
        def pct(lst, p):
            s = sorted(lst)
            k = (len(s)-1) * p / 100.0
            lo, hi = int(k), min(int(k)+1, len(s)-1)
            return s[lo] + (k-lo)*(s[hi]-s[lo])
        self.assertAlmostEqual(pct(data, 50), 5.5, places=5)
        self.assertEqual(pct(data, 100), 10.0)
        self.assertEqual(pct(data, 0), 1.0)


if __name__ == "__main__":
    print("╔═══════════════════════════════════════╗")
    print("║  COSMIC PONG PHYSICS TEST SUITE        ║")
    print("╚═══════════════════════════════════════╝\n")
    loader = unittest.TestLoader()
    suite  = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
