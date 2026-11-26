"""
Pre-flight mathematical 9:16 portrait camera framing, ZERO-OVERLAP sightline & STATION ISOLATION verifier
for Scientist #10: Benjamin Franklin V10 (1752 Stormy Kite, Leyden Jar & Copper Lightning Rod).
"""
import math
import numpy as np

RES_X, RES_Y = 1080, 1920
ASPECT = RES_X / RES_Y
SENSOR_W = 36.0
SENSOR_H = SENSOR_W / ASPECT  # 64.0mm with sensor_fit='HORIZONTAL'

KITE_POS = np.array([-0.44, 0.28, 2.38])
KITE_KEY_PLINTH = np.array([-0.52, 0.12, 0.88])
KEY_STAND_PLINTH = np.array([0.55, 0.08, 0.90])
LEYDEN_ANCHOR = np.array([-2.85, 0.06, 0.0])
EASEL_POS = np.array([-2.48, 0.08, 1.24])
STEEPLE_PLINTH = np.array([2.88, 0.08, 0.90])
SPIRE_ANCHOR = np.array([0.64, 0.14, 0.0])


def clamp01(x):
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def smoothstep(e0, e1, x):
    t = clamp01((x - e0) / max(1e-6, e1 - e0))
    return t * t * (3.0 - 2.0 * t)


def ease_out_quint(x):
    t = clamp01(x)
    return 1.0 - (1.0 - t) ** 5


def lerp(a, b, t):
    return a + (b - a) * t


def bezier_quad(p0, p1, p2, t):
    u = 1.0 - t
    return p0 * (u * u) + p1 * (2.0 * u * t) + p2 * (t * t)


def compute_beat(b_idx, t):
    if b_idx == 0:
        u = clamp01(t / 4.5)
        pos = bezier_quad(np.array([-0.82, -1.86, 1.32]), np.array([-0.79, -1.78, 1.36]), np.array([-0.76, -1.70, 1.38]), u)
        tgt = lerp(np.array([-0.79, 0.24, 1.46]), np.array([-0.78, 0.22, 1.38]), u)
        return pos, tgt, lerp(36.0, 38.0, u)
    if b_idx == 1:
        pan_u = ease_out_quint(clamp01((t - 6.95) / 1.1))
        pos = lerp(np.array([0.60, -2.18, 1.42]), np.array([0.52, -2.10, 1.42]), pan_u)
        tgt = lerp(np.array([0.57, 0.28, 1.32]), np.array([0.54, 0.30, 1.32]), pan_u)
        return pos, tgt, lerp(34.5, 34.0, pan_u)
    if b_idx == 2:
        u = clamp01((t - 9.8) / 5.7)
        pos = bezier_quad(np.array([-2.52, -1.78, 1.40]), np.array([-2.49, -1.68, 1.41]), np.array([-2.46, -1.62, 1.42]), u)
        tgt = lerp(np.array([-2.50, 0.18, 1.32]), np.array([-2.48, 0.20, 1.36]), smoothstep(10.6, 13.0, t))
        return pos, tgt, lerp(37.5, 39.0, u)
    if b_idx == 3:
        u = clamp01((t - 15.5) / 5.0)
        pos = bezier_quad(np.array([2.60, -1.92, 1.38]), np.array([2.64, -1.86, 1.39]), np.array([2.68, -1.82, 1.40]), u)
        tgt = np.array([2.60, 0.22, 1.34])
        return pos, tgt, lerp(34.5, 36.0, u)
    if b_idx == 4:
        u = clamp01((t - 20.5) / 5.0)
        pos = bezier_quad(np.array([0.26, -1.94, 1.36]), np.array([0.30, -1.88, 1.44]), np.array([0.34, -1.84, 1.50]), u)
        tgt = lerp(np.array([0.30, 0.24, 1.44]), np.array([0.32, 0.26, 1.52]), u)
        return pos, tgt, lerp(35.0, 36.0, u)
    u = clamp01((t - 25.5) / 4.5)
    pos = bezier_quad(np.array([0.55, -2.55, 1.52]), np.array([0.55, -2.72, 1.58]), np.array([0.55, -2.88, 1.62]), u)
    tgt = lerp(np.array([0.55, 0.30, 1.54]), np.array([0.55, 0.28, 1.52]), u)
    return pos, tgt, lerp(32.0, 30.5, u)


def project(cam_pos, tgt, lens_mm, pt):
    fwd = tgt - cam_pos
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, np.array([0.0, 0.0, 1.0]))
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    d = pt - cam_pos
    z = np.dot(d, fwd)
    x = np.dot(d, right)
    y = np.dot(d, up)
    ndc_x = (x / z) * (lens_mm / (SENSOR_W * 0.5))
    ndc_y = (y / z) * (lens_mm / (SENSOR_H * 0.5))
    return ndc_x, ndc_y, z


checks = [
    (
        0, 2.2,
        "Beat 1 Viral Hook: Stormy Meadow — Benjamin(L) + Silk Kite & Brass Key Lightning Strike(R)",
        {
            "BenjaminHead": np.array([-1.06, 0.36, 1.66]),
            "SilkKite": KITE_POS.copy(),
            "BrassKey": np.array([KITE_KEY_PLINTH[0], KITE_KEY_PLINTH[1], KITE_KEY_PLINTH[2] + 0.34]),
        },
        [("BenjaminHead", "BrassKey", 0.42), ("BenjaminHead", "SilkKite", 0.40)],
    ),
    (
        1, 5.5,
        "Beat 2a High-Voltage Debate: Benjamin(L) + William(R) + +Q/-Q Formula(C)",
        {
            "BenjaminHead": np.array([-0.02, 0.46, 1.66]),
            "WilliamHead": np.array([1.12, 0.46, 1.66]),
            "Formula_Charge": np.array([KEY_STAND_PLINTH[0], 0.20, 2.03]),
            "HeroBrassKey": np.array([KEY_STAND_PLINTH[0] + 0.02, KEY_STAND_PLINTH[1], KEY_STAND_PLINTH[2] + 0.31]),
        },
        [("BenjaminHead", "WilliamHead", 0.60), ("BenjaminHead", "Formula_Charge", 0.30)],
    ),
    (
        1, 8.2,
        "Beat 2b Knuckle Spark Proof: Benjamin(L) + William(R) + V=kQ/r Formula(C)",
        {
            "BenjaminHead": np.array([-0.02, 0.46, 1.66]),
            "WilliamHead": np.array([1.12, 0.46, 1.66]),
            "Formula_Volt": np.array([KEY_STAND_PLINTH[0], 0.20, 2.04]),
        },
        [("BenjaminHead", "WilliamHead", 0.60), ("BenjaminHead", "Formula_Volt", 0.30)],
    ),
    (
        2, 12.6,
        "Beat 3 Leyden Jar Station: Glass Leyden Jar(L) + Camera-Facing +/− Easel(C) + Benjamin(R)",
        {
            "BenjaminHead": np.array([-2.04, 0.44, 1.66]),
            "LeydenJarSphere": np.array([LEYDEN_ANCHOR[0], LEYDEN_ANCHOR[1], 1.62]),
            "ChargeEasel": EASEL_POS.copy(),
        },
        [("BenjaminHead", "LeydenJarSphere", 0.42), ("BenjaminHead", "ChargeEasel", 0.25)],
    ),
    (
        3, 17.8,
        "Beat 4 Copper Lightning Rod Proof: William Recoil(L) + Colonial Steeple & Rod(R)",
        {
            "WilliamHead": np.array([2.22, 0.54, 1.60]),
            "SteepleSpire": np.array([STEEPLE_PLINTH[0], STEEPLE_PLINTH[1], STEEPLE_PLINTH[2] + 0.50]),
            "CopperRodTip": np.array([STEEPLE_PLINTH[0], STEEPLE_PLINTH[1], STEEPLE_PLINTH[2] + 0.94]),
        },
        [("WilliamHead", "SteepleSpire", 0.42)],
    ),
    (
        4, 23.0,
        "Beat 5 Modern Electric Age: Benjamin(L) + Skyscraper Spire & Edison Glass Bulb(R)",
        {
            "BenjaminHead": np.array([-0.10, 0.50, 1.66]),
            "EdisonBulb": np.array([SPIRE_ANCHOR[0], SPIRE_ANCHOR[1], 1.44]),
            "GridRingEdge": np.array([SPIRE_ANCHOR[0] + 0.24, SPIRE_ANCHOR[1], 1.44]),
        },
        [("BenjaminHead", "EdisonBulb", 0.42)],
    ),
    (
        5, 28.0,
        "Beat 6 Finale Monument: Benjamin(L) + William(R) + Centered Electric Spire + Sky Title",
        {
            "BenjaminHead": np.array([-0.14, 0.48, 1.66]),
            "WilliamHead": np.array([1.24, 0.48, 1.66]),
            "EdisonBulb": np.array([0.55, SPIRE_ANCHOR[1], 1.44]),
            "TitleRight": np.array([1.18, 0.24, 2.52]),
        },
        [("BenjaminHead", "WilliamHead", 0.60), ("BenjaminHead", "EdisonBulb", 0.30)],
    ),
]


def main():
    ok = True
    for b_idx, t, label, pts, pairs in checks:
        cam, tgt, lens = compute_beat(b_idx, t)
        print(f"\n[{label} (t={t:.1f}s)] cam={np.round(cam, 2)} tgt={np.round(tgt, 2)} lens={lens:.1f}mm")
        proj = {}
        for name, pt in pts.items():
            nx, ny, z = project(cam, tgt, lens, pt)
            proj[name] = (nx, ny, z)
            in_bounds = (abs(nx) <= 0.85) and (-0.50 <= ny <= 0.72) and (z > 0.5)
            status = "OK" if in_bounds else "OUT_OF_FRAME!"
            if not in_bounds:
                ok = False
            print(f"  {name:16s}: ndcX={nx:+.2f}  ndcY={ny:+.2f}  depth={z:.2f}m  [{status}]")
        for a, b, min_dx in pairs:
            dx = abs(proj[a][0] - proj[b][0])
            sep_ok = dx >= min_dx
            if not sep_ok:
                ok = False
            print(f"  SEPARATION {a} <-> {b}: |dX|={dx:.2f} (min {min_dx:.2f}) [{'CLEAR!' if sep_ok else 'OVERLAP!'}]")

    # Camera-facing display check (AGENTS.md Section 3: dot(display_normal, to_camera) > +0.55)
    cam3, _, _ = compute_beat(2, 12.6)
    easel_norm = np.array([math.sin(math.radians(38.0)), -math.cos(math.radians(38.0)), 0.0])
    to_cam3 = (cam3 - EASEL_POS)
    to_cam3 /= np.linalg.norm(to_cam3)
    dot_easel = float(np.dot(easel_norm, to_cam3))
    print(f"\n[CAMERA-FACING DISPLAY CHECK (AGENTS.md Section 3)]")
    print(f"  Beat 3 Charge Easel dot(normal, to_cam) = {dot_easel:+.3f} (min +0.55) [{'CLEAR!' if dot_easel > 0.55 else 'FAIL!'}]")
    if dot_easel <= 0.55:
        ok = False

    # Station isolation checks
    print("\n[STATION ISOLATION CHECKS (ZERO EDGE INTRUSION)]")
    iso_checks = [
        ("Beat 1: Leyden Easel right edge OUTSIDE left frame", 0, 1.0, np.array([-2.25, 0.08, 1.24]), -1.05),
        ("Beat 3: Kite Plinth left edge OUTSIDE right frame", 2, 12.6, np.array([-0.82, 0.12, 0.88]), +1.05),
        ("Beat 4: Key Stand Plinth right edge OUTSIDE left frame", 3, 17.8, np.array([0.85, 0.08, 0.90]), -1.05),
    ]
    for desc, b_idx, t, pt, thresh in iso_checks:
        cam, tgt, lens = compute_beat(b_idx, t)
        nx, _, _ = project(cam, tgt, lens, pt)
        iso_ok = (nx < thresh) if thresh < 0 else (nx > thresh)
        if not iso_ok:
            ok = False
        print(f"  {desc}: ndcX={nx:+.2f} ({'OUTSIDE' if iso_ok else 'INTRUDING!'})")

    if not ok:
        raise SystemExit("FAILED: Framing / sightline / isolation / display check failed!")
    print("\nPASSED: 100% V10 Benjamin Franklin ZERO-OVERLAP Sightlines + Camera-Facing Easel + Station Isolation across ALL 6 Beats!")


if __name__ == "__main__":
    main()
