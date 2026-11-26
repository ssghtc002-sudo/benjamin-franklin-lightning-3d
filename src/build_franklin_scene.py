"""
Scientist #10: Benjamin Franklin (1752) — Catching Lightning With a Kite, Leyden Jar & Copper Lightning Rod
V10 Viral Cinema Master Scene Builder (Blender 4.2.3 LTS Cycles OPTIX + GPU OIDN)

Follows 100% of AGENTS.md V10 Cinema Production Standards:
  - Photoreal MPFB2 eyes (visible_shadow=False, per-actor EnhancedEye, Fresnel glossy cornea, 0.42m softbox catchlight, jaw <= 14 deg)
  - Benjamin Franklin's iconic 3D Brass Spectacles parented to head bone (transparent shadow-bypass lenses)
  - Crisp 2-Zone Brushed-Gold/Cyan 3D Formulas (+Q ⚡ −Q, V = k · Q / r) & 2-Tier Sky Monument on exact DOF plane (Y=0.20, Z=2.03/2.52)
  - Open-ended (end_fill_type='NOTHING') front-face Additive Volumetric Lightning Bolts, Knuckle Spark Arc & Leyden Jar Plasma
  - Refractive Glass Shadow Bypass (LightPath.Is Shadow Ray -> Transparent BSDF) on Leyden Jar, Edison Bulb & Spectacles
  - Camera-facing Colonial Slate Charge Easel (+38 deg, dot > +0.75) & zero hand-to-prop clipping (>= 0.15m clearance)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from franklin_world_v10 import (
    FLOOR_Z,
    KEY_STAND_PLINTH,
    KITE_KEY_PLINTH,
    KITE_POS,
    LEYDEN_ANCHOR,
    SPIRE_ANCHOR,
    STEEPLE_PLINTH,
    animate_franklin_world,
    build_franklin_world,
    clamp01,
    lerp,
    set_bsdf,
    smoothstep,
)
from mpfb_characters import (
    apply_arm_with_clavicle,
    apply_facial_acting,
    apply_hand_gesture,
    apply_natural_stance,
    create_realistic_scientist,
    set_bone_char_rot,
)

# ============================================================================
# GLOBAL RENDER & CLI ARGUMENTS
# ============================================================================
RES_X, RES_Y = 1080, 1920
FPS = 24
DURATION = 30.0
TOTAL_FRAMES = int(round(DURATION * FPS))  # 720 frames
FONT_PATH = str(PROJECT_ROOT / "subtitles" / "fonts" / "DejaVuSans-Bold.ttf")
MANIFEST_PATH = PROJECT_ROOT / "audio" / "output" / "voice_manifest.json"


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--frames-dir", default=str(PROJECT_ROOT / "render_frames"))
    p.add_argument("--start-frame", type=int, default=1)
    p.add_argument("--end-frame", type=int, default=TOTAL_FRAMES)
    p.add_argument("--samples", type=int, default=12)
    p.add_argument("--scale", type=int, default=100)
    p.add_argument("--preview", action="store_true")
    p.add_argument("--device", default="OPTIX")
    return p.parse_args(argv)


def ease_out_quint(x: float) -> float:
    t = clamp01(x)
    return 1.0 - (1.0 - t) ** 5


def bezier_quad(p0: Vector, p1: Vector, p2: Vector, t: float) -> Vector:
    u = 1.0 - t
    return p0 * (u * u) + p1 * (2.0 * u * t) + p2 * (t * t)


def load_voice_manifest():
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {"fps": 30, "lipSync": {}, "lipNarrow": {}}


def sample_lip(manifest: dict, speaker: str, t: float) -> tuple[float, float]:
    lip_fps = float(manifest.get("fps", 30))
    idx = max(0, int(round(t * lip_fps)))
    ls = manifest.get("lipSync", {}).get(speaker, [])
    ln = manifest.get("lipNarrow", {}).get(speaker, [])
    v_lip = float(ls[min(len(ls) - 1, idx)]) if ls else 0.0
    v_nar = float(ln[min(len(ln) - 1, idx)]) if ln else 0.0
    return v_lip, v_nar


# ============================================================================
# V10 AGENTS.md SHADER FACTORY (2-ZONE FORMULAS, ADDITIVE VOLUMETRICS, GLASS)
# ============================================================================
def make_pbr_mat(name: str, rgb, metallic: float = 0.0, rough: float = 0.4, coat: float = 0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    set_bsdf(bsdf, "Base Color", (*rgb, 1.0))
    set_bsdf(bsdf, "Metallic", metallic)
    set_bsdf(bsdf, "Roughness", rough)
    if coat > 0.0:
        set_bsdf(bsdf, "Coat Weight", coat)
        set_bsdf(bsdf, "Coat Roughness", 0.08)
    return mat


def make_emissive_mat(name: str, rgb, strength: float = 2.4):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*rgb, 1.0)
    em.inputs["Strength"].default_value = strength
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return mat


def make_crystal_glass_mat(name: str, tint=(0.90, 0.97, 1.0), ior: float = 1.52, rough: float = 0.03):
    """AGENTS.md Section 3: Refractive glass with mandatory LightPath.Is Shadow Ray -> Transparent BSDF bypass!"""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    out = nt.nodes["Material Output"]
    set_bsdf(bsdf, "Base Color", (*tint, 1.0))
    set_bsdf(bsdf, "Roughness", rough)
    set_bsdf(bsdf, "IOR", ior)
    set_bsdf(bsdf, "Transmission Weight", 0.96)
    set_bsdf(bsdf, "Transmission", 0.96)
    set_bsdf(bsdf, "Coat Weight", 1.0)
    set_bsdf(bsdf, "Coat Roughness", 0.012)

    lw = nt.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.20
    pw = nt.nodes.new("ShaderNodeMath")
    pw.operation = "POWER"
    pw.inputs[1].default_value = 3.0
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.clamp = True
    mr.inputs["From Min"].default_value = 0.16
    mr.inputs["From Max"].default_value = 1.0
    mr.inputs["To Min"].default_value = 0.0
    mr.inputs["To Max"].default_value = 1.65
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (0.76, 0.94, 1.0, 1.0)
    add_sh = nt.nodes.new("ShaderNodeAddShader")

    lp = nt.nodes.new("ShaderNodeLightPath")
    transp = nt.nodes.new("ShaderNodeBsdfTransparent")
    transp.inputs["Color"].default_value = (0.96, 0.98, 1.0, 1.0)
    sh_mix = nt.nodes.new("ShaderNodeMixShader")

    nt.links.new(lw.outputs["Fresnel"], pw.inputs[0])
    nt.links.new(pw.outputs["Value"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], em.inputs["Strength"])
    nt.links.new(bsdf.outputs["BSDF"], add_sh.inputs[0])
    nt.links.new(em.outputs["Emission"], add_sh.inputs[1])
    nt.links.new(lp.outputs["Is Shadow Ray"], sh_mix.inputs["Fac"])
    nt.links.new(add_sh.outputs["Shader"], sh_mix.inputs[1])
    nt.links.new(transp.outputs["BSDF"], sh_mix.inputs[2])
    nt.links.new(sh_mix.outputs["Shader"], out.inputs["Surface"])
    return mat


def make_additive_lightning_mat(name: str, core_rgb=(0.68, 0.94, 1.0), strength: float = 3.4):
    """AGENTS.md Section 3: Front-facing Camera-Ray Additive Shader for razor-sharp volumetric lightning & electric arcs."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    geom = nt.nodes.new("ShaderNodeNewGeometry")
    lp = nt.nodes.new("ShaderNodeLightPath")
    lw = nt.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.35

    inv_bf = nt.nodes.new("ShaderNodeMath")
    inv_bf.operation = "SUBTRACT"
    inv_bf.inputs[0].default_value = 1.0
    inv_bf.use_clamp = True

    cam_front = nt.nodes.new("ShaderNodeMath")
    cam_front.operation = "MULTIPLY"

    core_falloff = nt.nodes.new("ShaderNodeMath")
    core_falloff.operation = "SUBTRACT"
    core_falloff.inputs[0].default_value = 1.0
    core_falloff.use_clamp = True

    pw = nt.nodes.new("ShaderNodeMath")
    pw.operation = "POWER"
    pw.inputs[1].default_value = 1.35

    mul_vis = nt.nodes.new("ShaderNodeMath")
    mul_vis.operation = "MULTIPLY"

    mul_str = nt.nodes.new("ShaderNodeMath")
    mul_str.operation = "MULTIPLY"
    mul_str.inputs[1].default_value = strength

    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*core_rgb, 1.0)
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    tr.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    add_sh = nt.nodes.new("ShaderNodeAddShader")

    nt.links.new(geom.outputs["Backfacing"], inv_bf.inputs[1])
    nt.links.new(lp.outputs["Is Camera Ray"], cam_front.inputs[0])
    nt.links.new(inv_bf.outputs["Value"], cam_front.inputs[1])
    nt.links.new(lw.outputs["Facing"], core_falloff.inputs[1])
    nt.links.new(core_falloff.outputs["Value"], pw.inputs[0])
    nt.links.new(cam_front.outputs["Value"], mul_vis.inputs[0])
    nt.links.new(pw.outputs["Value"], mul_vis.inputs[1])
    nt.links.new(mul_vis.outputs["Value"], mul_str.inputs[0])
    nt.links.new(mul_str.outputs["Value"], em.inputs["Strength"])
    nt.links.new(tr.outputs["BSDF"], add_sh.inputs[0])
    nt.links.new(em.outputs["Emission"], add_sh.inputs[1])
    nt.links.new(add_sh.outputs["Shader"], out.inputs["Surface"])
    return mat


def make_crisp_formula_mat(name: str, face_rgb=(1.0, 0.80, 0.28), strength: float = 1.75):
    """AGENTS.md Section 2: Object-space |N.z| 2-zone brushed-metallic face + dark obsidian-bronze extrusion."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")

    geom = nt.nodes.new("ShaderNodeNewGeometry")
    vec_tr = nt.nodes.new("ShaderNodeVectorTransform")
    vec_tr.vector_type = "NORMAL"
    vec_tr.convert_from = "WORLD"
    vec_tr.convert_to = "OBJECT"
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    abs_z = nt.nodes.new("ShaderNodeMath")
    abs_z.operation = "ABSOLUTE"

    face_mask = nt.nodes.new("ShaderNodeMapRange")
    face_mask.clamp = True
    face_mask.interpolation_type = "SMOOTHSTEP"
    face_mask.inputs["From Min"].default_value = 0.82
    face_mask.inputs["From Max"].default_value = 0.94

    face_bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    set_bsdf(face_bsdf, "Base Color", (*face_rgb, 1.0))
    set_bsdf(face_bsdf, "Metallic", 0.85)
    set_bsdf(face_bsdf, "Roughness", 0.24)
    set_bsdf(face_bsdf, "Emission Color", (*face_rgb, 1.0))
    set_bsdf(face_bsdf, "Emission Strength", strength)

    side_bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    set_bsdf(side_bsdf, "Base Color", (0.04, 0.032, 0.025, 1.0))
    set_bsdf(side_bsdf, "Metallic", 0.92)
    set_bsdf(side_bsdf, "Roughness", 0.34)

    mix_sh = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(geom.outputs["Normal"], vec_tr.inputs["Vector"])
    nt.links.new(vec_tr.outputs["Vector"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["Z"], abs_z.inputs[0])
    nt.links.new(abs_z.outputs["Value"], face_mask.inputs["Value"])
    nt.links.new(face_mask.outputs["Result"], mix_sh.inputs["Fac"])
    nt.links.new(side_bsdf.outputs["BSDF"], mix_sh.inputs[1])
    nt.links.new(face_bsdf.outputs["BSDF"], mix_sh.inputs[2])
    nt.links.new(mix_sh.outputs["Shader"], out.inputs["Surface"])
    return mat


def make_text_keyline_mat(name: str = "ObsidianKeylineMat"):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    set_bsdf(bsdf, "Base Color", (0.012, 0.014, 0.022, 1.0))
    set_bsdf(bsdf, "Roughness", 0.72)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def make_formula_halo_mat(name: str = "FormulaCapsuleHaloMat", opacity: float = 0.76):
    """AGENTS.md Section 2: Capsule (x^4 + y^2) dark obsidian sky veil halo for instant contrast."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")

    sub_x = nt.nodes.new("ShaderNodeMath")
    sub_x.operation = "SUBTRACT"
    sub_x.inputs[1].default_value = 0.5
    mul_x = nt.nodes.new("ShaderNodeMath")
    mul_x.operation = "MULTIPLY"
    mul_x.inputs[1].default_value = 2.0
    pow_x = nt.nodes.new("ShaderNodeMath")
    pow_x.operation = "POWER"
    pow_x.inputs[1].default_value = 4.0

    sub_y = nt.nodes.new("ShaderNodeMath")
    sub_y.operation = "SUBTRACT"
    sub_y.inputs[1].default_value = 0.5
    mul_y = nt.nodes.new("ShaderNodeMath")
    mul_y.operation = "MULTIPLY"
    mul_y.inputs[1].default_value = 2.0
    pow_y = nt.nodes.new("ShaderNodeMath")
    pow_y.operation = "POWER"
    pow_y.inputs[1].default_value = 2.0

    add_r = nt.nodes.new("ShaderNodeMath")
    add_r.operation = "ADD"

    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.clamp = True
    mr.interpolation_type = "SMOOTHSTEP"
    mr.inputs["From Min"].default_value = 0.25
    mr.inputs["From Max"].default_value = 1.0
    mr.inputs["To Min"].default_value = opacity
    mr.inputs["To Max"].default_value = 0.0

    lp = nt.nodes.new("ShaderNodeLightPath")
    cam_op = nt.nodes.new("ShaderNodeMath")
    cam_op.operation = "MULTIPLY"

    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    tr.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    dark = nt.nodes.new("ShaderNodeEmission")
    dark.inputs["Color"].default_value = (0.008, 0.014, 0.028, 1.0)
    dark.inputs["Strength"].default_value = 0.15
    mix = nt.nodes.new("ShaderNodeMixShader")

    nt.links.new(tc.outputs["Generated"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["X"], sub_x.inputs[0])
    nt.links.new(sub_x.outputs["Value"], mul_x.inputs[0])
    nt.links.new(mul_x.outputs["Value"], pow_x.inputs[0])
    nt.links.new(sep.outputs["Y"], sub_y.inputs[0])
    nt.links.new(sub_y.outputs["Value"], mul_y.inputs[0])
    nt.links.new(mul_y.outputs["Value"], pow_y.inputs[0])
    nt.links.new(pow_x.outputs["Value"], add_r.inputs[0])
    nt.links.new(pow_y.outputs["Value"], add_r.inputs[1])
    nt.links.new(add_r.outputs["Value"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], cam_op.inputs[0])
    nt.links.new(lp.outputs["Is Camera Ray"], cam_op.inputs[1])
    nt.links.new(cam_op.outputs["Value"], mix.inputs["Fac"])
    nt.links.new(tr.outputs["BSDF"], mix.inputs[1])
    nt.links.new(dark.outputs["Emission"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    return mat


# ============================================================================
# GEOMETRY PRIMITIVES (OPEN-ENDED VOLUMETRIC BEAMS, LIGHTNING BOLTS, 3D TEXT)
# ============================================================================
def link_obj(scene, obj):
    if obj.name not in scene.collection.objects:
        scene.collection.objects.link(obj)
    return obj


def add_mesh(scene, name: str, bm: bmesh.types.BMesh, mat, loc=(0, 0, 0), rot=(0, 0, 0), smooth=True, shadow=True):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = Vector(loc)
    obj.rotation_euler = Euler(rot, "XYZ")
    if smooth:
        for p in mesh.polygons:
            p.use_smooth = True
    if mat is not None:
        obj.data.materials.append(mat)
    obj.visible_shadow = shadow
    return link_obj(scene, obj)


def add_open_beam_unit(scene, name: str, mat, r1: float = 0.015, r2: float = 0.015, segs: int = 12):
    """Unit-length Z in [0..1] open-ended volumetric cylinder/cone (end_fill_type='NOTHING' per AGENTS.md!)."""
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm, cap_ends=False, cap_tris=False, segments=segs,
        radius1=r1, radius2=r2, depth=1.0,
        matrix=Matrix.Translation((0.0, 0.0, 0.5)),
    )
    return add_mesh(scene, name, bm, mat, smooth=True, shadow=False)


def orient_beam(obj, p0: Vector, p1: Vector, radius_scale: float = 1.0, frame: int | None = None):
    d = p1 - p0
    L = max(1e-4, d.length)
    q = d.normalized().to_track_quat("Z", "Y")
    obj.location = p0
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = q
    obj.scale = (radius_scale, radius_scale, L)
    if frame is not None:
        obj.keyframe_insert(data_path="location", frame=frame)
        obj.keyframe_insert(data_path="rotation_quaternion", frame=frame)
        obj.keyframe_insert(data_path="scale", frame=frame)


def build_jagged_lightning_bolt(scene, name: str, p_start: Vector, p_end: Vector, mat, radius: float = 0.018, segments: int = 10, jitter: float = 0.12, seed: int = 42, add_branches: bool = True):
    """Multi-segment jagged 3D open-ended volumetric lightning bolt mesh."""
    rng = random.Random(seed)
    pts = [p_start.copy()]
    d_vec = p_end - p_start
    perp1 = d_vec.cross(Vector((0.0, 1.0, 0.0)))
    if perp1.length < 1e-4:
        perp1 = d_vec.cross(Vector((1.0, 0.0, 0.0)))
    perp1.normalize()
    perp2 = d_vec.cross(perp1).normalized()

    for i in range(1, segments):
        u = i / float(segments)
        env = math.sin(math.pi * u)
        base = p_start.lerp(p_end, u)
        off = perp1 * rng.uniform(-jitter, jitter) * env + perp2 * rng.uniform(-jitter * 0.45, jitter * 0.45) * env
        pts.append(base + off)
    pts.append(p_end.copy())

    bm = bmesh.new()

    def _add_tube(a: Vector, b: Vector, r_a: float, r_b: float):
        dv = b - a
        ln = dv.length
        if ln < 1e-5:
            return
        q = dv.normalized().to_track_quat("Z", "Y")
        m = Matrix.Translation(a) @ q.to_matrix().to_4x4() @ Matrix.Translation((0.0, 0.0, ln * 0.5))
        bmesh.ops.create_cone(bm, cap_ends=False, cap_tris=False, segments=8, radius1=r_a, radius2=r_b, depth=ln, matrix=m)

    for i in range(len(pts) - 1):
        u0 = i / float(len(pts) - 1)
        u1 = (i + 1) / float(len(pts) - 1)
        _add_tube(pts[i], pts[i + 1], radius * (1.15 - 0.35 * u0), radius * (1.15 - 0.35 * u1))

    if add_branches:
        for b_idx in (2, 4, 6):
            if b_idx < len(pts) - 1:
                bp0 = pts[b_idx]
                side = 1.0 if (b_idx % 2 == 0) else -1.0
                bp1 = bp0 + perp1 * (side * rng.uniform(0.14, 0.28)) + d_vec.normalized() * rng.uniform(0.18, 0.34)
                bp2 = bp1 + perp1 * (side * rng.uniform(0.10, 0.22)) + d_vec.normalized() * rng.uniform(0.16, 0.28)
                _add_tube(bp0, bp1, radius * 0.55, radius * 0.32)
                _add_tube(bp1, bp2, radius * 0.32, radius * 0.10)

    return add_mesh(scene, name, bm, mat, smooth=True, shadow=False)


def create_crisp_3d_text(scene, name: str, body: str, size: float, loc: Vector, face_mat, keyline_mat, halo_mat, halo_w: float, halo_h: float):
    """AGENTS.md Section 2: Crisp shallow-extrusion 3D text + recessed obsidian keyline + capsule sky veil."""
    root = bpy.data.objects.new(f"{name}_Root", None)
    root.location = loc
    link_obj(scene, root)

    font = bpy.data.fonts.load(FONT_PATH, check_existing=True)

    def _make_curve(cname: str, extrude: float, bevel: float, mat, dy: float):
        cd = bpy.data.curves.new(f"{cname}_Curve", type="FONT")
        cd.body = body
        cd.font = font
        cd.size = size
        cd.align_x = "CENTER"
        cd.align_y = "CENTER"
        cd.extrude = extrude
        cd.bevel_depth = bevel
        cd.bevel_resolution = 2
        obj = bpy.data.objects.new(cname, cd)
        obj.location = Vector((0.0, dy, 0.0))
        obj.rotation_euler = Euler((math.radians(90.0), 0.0, 0.0), "XYZ")
        obj.data.materials.append(mat)
        obj.visible_shadow = False
        obj.parent = root
        return link_obj(scene, obj)

    _make_curve(f"{name}_Face", extrude=0.0045, bevel=0.00055, mat=face_mat, dy=0.0)
    _make_curve(f"{name}_Keyline", extrude=0.0042, bevel=0.0018, mat=keyline_mat, dy=0.0065)

    # Capsule sky veil backdrop
    bm_h = bmesh.new()
    bmesh.ops.create_grid(
        bm_h, x_segments=1, y_segments=1, size=0.5,
        matrix=Matrix.Diagonal((halo_w, halo_h, 1.0, 1.0)),
    )
    halo = add_mesh(scene, f"{name}_Halo", bm_h, halo_mat, loc=(0.0, 0.016, 0.0), rot=(math.radians(90.0), 0.0, 0.0), smooth=False, shadow=False)
    halo.parent = root
    return root


# ============================================================================
# BENJAMIN FRANKLIN'S ICONIC 3D BRASS SPECTACLES (PARENTED TO HEAD BONE!)
# ============================================================================
def attach_franklin_spectacles(scene, rig, brass_mat, lens_glass_mat):
    if rig is None or "head" not in rig.pose.bones or "eye.L" not in rig.data.bones or "eye.R" not in rig.data.bones:
        return None
    bpy.context.view_layer.update()
    el = rig.data.bones["eye.L"].head_local.copy()
    er = rig.data.bones["eye.R"].head_local.copy()
    ipd_half = max(0.028, min(0.038, abs(el.x - er.x) * 0.5))
    # Bridge sits 24mm in front of eyeball centers (-Y is face front in MPFB2!)
    bridge_arm = (el + er) * 0.5 + Vector((0.0, -0.024, 0.0))

    bm_fr = bmesh.new()
    for sx in (-ipd_half, ipd_half):
        segs = 24
        r_maj = 0.0185
        r_min = 0.0015
        ring_prev = None
        first_ring = None
        for i in range(segs):
            a = 2.0 * math.pi * i / segs
            cx = sx + r_maj * math.cos(a)
            cz = r_maj * math.sin(a)
            ring = []
            for j in range(6):
                b = 2.0 * math.pi * j / 6
                rx = cx + r_min * math.cos(b) * math.cos(a)
                ry = r_min * math.sin(b)
                rz = cz + r_min * math.cos(b) * math.sin(a)
                ring.append(bm_fr.verts.new((rx, ry, rz)))
            if ring_prev is not None:
                for j in range(6):
                    jn = (j + 1) % 6
                    bm_fr.faces.new((ring_prev[j], ring_prev[jn], ring[jn], ring[j]))
            else:
                first_ring = ring
            ring_prev = ring
        for j in range(6):
            jn = (j + 1) % 6
            bm_fr.faces.new((ring_prev[j], ring_prev[jn], first_ring[jn], first_ring[j]))

    # Nose bridge + slim temples back toward ears (+Y)
    bmesh.ops.create_cube(
        bm_fr, size=1.0,
        matrix=Matrix.Translation((0.0, 0.0, 0.004)) @ Matrix.Diagonal((ipd_half * 0.90, 0.0024, 0.0024, 1.0)),
    )
    for sx in (-(ipd_half + 0.019), ipd_half + 0.019):
        bmesh.ops.create_cube(
            bm_fr, size=1.0,
            matrix=Matrix.Translation((sx, 0.052, 0.002)) @ Matrix.Diagonal((0.0022, 0.104, 0.0022, 1.0)),
        )
    frame_obj = add_mesh(scene, "FranklinBrassSpectacles", bm_fr, brass_mat, smooth=True, shadow=False)

    bm_ln = bmesh.new()
    for sx in (-ipd_half, ipd_half):
        bmesh.ops.create_cone(
            bm_ln, cap_ends=True, cap_tris=False, segments=20,
            radius1=0.0178, radius2=0.0178, depth=0.0012,
            matrix=Matrix.Translation((sx, 0.0, 0.0)) @ Matrix.Rotation(math.radians(90.0), 4, "X"),
        )
    lens_obj = add_mesh(scene, "FranklinSpectacleLenses", bm_ln, lens_glass_mat, smooth=True, shadow=False)
    lens_obj.parent = frame_obj

    # Place millimeter-exact in world space & lock via CHILD_OF head bone constraint!
    world_m = rig.matrix_world @ Matrix.Translation(bridge_arm)
    frame_obj.matrix_world = world_m
    head_world = rig.matrix_world @ rig.pose.bones["head"].matrix
    con = frame_obj.constraints.new("CHILD_OF")
    con.target = rig
    con.subtarget = "head"
    con.inverse_matrix = head_world.inverted()
    return frame_obj


# ============================================================================
# HERO 3D PHYSICS PROPS ACROSS ALL 6 VIRAL BEATS
# ============================================================================
def build_brass_key(scene, name: str, loc: Vector, brass_mat, scale: float = 1.0):
    root = bpy.data.objects.new(name, None)
    root.location = loc
    root.scale = (scale, scale, scale)
    link_obj(scene, root)

    bm = bmesh.new()
    # Ornate colonial bow (ring top)
    segs = 20
    for i in range(segs):
        a0 = 2.0 * math.pi * i / segs
        a1 = 2.0 * math.pi * (i + 1) / segs
        p0 = Vector((0.026 * math.cos(a0), 0.0, 0.052 + 0.026 * math.sin(a0)))
        p1 = Vector((0.026 * math.cos(a1), 0.0, 0.052 + 0.026 * math.sin(a1)))
        mid = (p0 + p1) * 0.5
        q = (p1 - p0).normalized().to_track_quat("Z", "Y")
        bmesh.ops.create_cone(
            bm, cap_ends=True, cap_tris=False, segments=8,
            radius1=0.0055, radius2=0.0055, depth=(p1 - p0).length * 1.08,
            matrix=Matrix.Translation(mid) @ q.to_matrix().to_4x4(),
        )
    # Key shaft
    bmesh.ops.create_cone(
        bm, cap_ends=True, cap_tris=False, segments=12,
        radius1=0.0055, radius2=0.0065, depth=0.115,
        matrix=Matrix.Translation((0.0, 0.0, -0.028)),
    )
    # Key bit teeth
    bmesh.ops.create_cube(
        bm, size=1.0,
        matrix=Matrix.Translation((0.018, 0.0, -0.068)) @ Matrix.Diagonal((0.028, 0.007, 0.026, 1.0)),
    )
    bmesh.ops.create_cube(
        bm, size=1.0,
        matrix=Matrix.Translation((0.022, 0.0, -0.045)) @ Matrix.Diagonal((0.020, 0.007, 0.010, 1.0)),
    )
    mesh_obj = add_mesh(scene, f"{name}_Mesh", bm, brass_mat, smooth=True, shadow=True)
    mesh_obj.parent = root
    return root


def build_station1_kite_and_key(scene, brass_mat, oak_mat, lightning_mat, gold_spark_mat):
    """Beat 1: Diamond Crimson-Silk Kite + Wet Hemp String + Hanging Brass Key + Multi-Branch Lightning Strike."""
    kite_root = bpy.data.objects.new("FranklinKite_Root", None)
    kite_root.location = KITE_POS
    link_obj(scene, kite_root)

    silk_mat = make_pbr_mat("KiteCrimsonSilk", (0.68, 0.11, 0.08), metallic=0.0, rough=0.45, coat=0.25)
    trim_mat = make_pbr_mat("KiteCreamSilk", (0.88, 0.80, 0.62), metallic=0.0, rough=0.50)

    # Diamond sail
    bm_sail = bmesh.new()
    v_top = bm_sail.verts.new((0.0, 0.0, 0.34))
    v_bot = bm_sail.verts.new((0.0, 0.0, -0.44))
    v_lft = bm_sail.verts.new((-0.26, -0.03, 0.02))
    v_rgt = bm_sail.verts.new((0.26, -0.03, 0.02))
    v_ctr = bm_sail.verts.new((0.0, -0.05, 0.02))
    bm_sail.faces.new((v_top, v_rgt, v_ctr))
    bm_sail.faces.new((v_top, v_ctr, v_lft))
    bm_sail.faces.new((v_bot, v_lft, v_ctr))
    bm_sail.faces.new((v_bot, v_ctr, v_rgt))
    sail = add_mesh(scene, "FranklinKite_Sail", bm_sail, silk_mat, smooth=False, shadow=True)
    sail.parent = kite_root

    # Crossed cedar spars + pointed iron lightning wire at top of kite!
    bm_sp = bmesh.new()
    bmesh.ops.create_cone(bm_sp, cap_ends=True, cap_tris=False, segments=8, radius1=0.008, radius2=0.008, depth=0.78, matrix=Matrix.Translation((0, 0.006, -0.05)))
    bmesh.ops.create_cone(
        bm_sp, cap_ends=True, cap_tris=False, segments=8, radius1=0.007, radius2=0.007, depth=0.52,
        matrix=Matrix.Translation((0, 0.006, 0.02)) @ Matrix.Rotation(math.radians(90.0), 4, "Y"),
    )
    spars = add_mesh(scene, "FranklinKite_Spars", bm_sp, oak_mat, smooth=True, shadow=True)
    spars.parent = kite_root

    # Pointed brass lightning collector needle at kite apex
    bm_pin = bmesh.new()
    bmesh.ops.create_cone(bm_pin, cap_ends=True, cap_tris=False, segments=10, radius1=0.007, radius2=0.001, depth=0.16, matrix=Matrix.Translation((0, 0, 0.42)))
    pin = add_mesh(scene, "FranklinKite_Spike", bm_pin, brass_mat, smooth=True, shadow=False)
    pin.parent = kite_root

    # Flowing kite tail bows
    bm_tail = bmesh.new()
    for i in range(4):
        tz = -0.52 - i * 0.14
        tx = 0.06 * math.sin(i * 1.4)
        bmesh.ops.create_cube(bm_tail, size=1.0, matrix=Matrix.Translation((tx, 0.02, tz)) @ Matrix.Diagonal((0.09, 0.012, 0.028, 1.0)))
    tail = add_mesh(scene, "FranklinKite_Tail", bm_tail, trim_mat, smooth=False, shadow=False)
    tail.parent = kite_root

    # Wooden kite-string anchor post & glowing brass key above KITE_KEY_PLINTH
    key_pos = Vector((KITE_KEY_PLINTH.x, KITE_KEY_PLINTH.y, KITE_KEY_PLINTH.z + 0.34))
    key_obj = build_brass_key(scene, "Beat1_BrassKey", key_pos, brass_mat, scale=1.35)

    # Taut hemp string from kite down to brass key + glowing electric charge sheath
    hemp_mat = make_pbr_mat("WetHempTwine", (0.48, 0.40, 0.28), rough=0.82)
    string_beam = add_open_beam_unit(scene, "KiteWetString", hemp_mat, r1=0.0045, r2=0.0045, segs=8)
    orient_beam(string_beam, key_pos + Vector((0, 0, 0.08)), KITE_POS + Vector((0, 0, -0.05)), 1.0)

    charge_sheath = add_open_beam_unit(scene, "KiteStringElectricGlow", lightning_mat, r1=0.014, r2=0.014, segs=10)
    orient_beam(charge_sheath, key_pos + Vector((0, 0, 0.06)), KITE_POS + Vector((0, 0, 0.44)), 0.001)

    # Blazing sky-to-kite multi-branch lightning bolt!
    sky_bolt = build_jagged_lightning_bolt(
        scene, "Beat1_SkyLightningBolt",
        KITE_POS + Vector((0.32, 0.24, 2.35)),
        KITE_POS + Vector((0.0, 0.0, 0.46)),
        lightning_mat, radius=0.028, segments=11, jitter=0.18, seed=1752, add_branches=True,
    )

    # Corona spark ring around Brass Key when lightning hits!
    bm_cor = bmesh.new()
    bmesh.ops.create_icosphere(bm_cor, subdivisions=2, radius=0.095)
    key_corona = add_mesh(scene, "Beat1_KeyCorona", bm_cor, lightning_mat, loc=key_pos, smooth=True, shadow=False)

    # 12 burst spark needles around key
    sparks = []
    rng = random.Random(17521)
    for i in range(12):
        sp = add_open_beam_unit(scene, f"Beat1_KeySpark_{i:02d}", gold_spark_mat if i % 3 == 0 else lightning_mat, r1=0.006, r2=0.001, segs=6)
        ang = 2.0 * math.pi * i / 12.0
        dir_v = Vector((math.cos(ang), rng.uniform(-0.35, 0.35), math.sin(ang))).normalized()
        sparks.append((sp, dir_v, rng.uniform(0.14, 0.28)))

    return {
        "kite_root": kite_root,
        "key_obj": key_obj,
        "key_pos": key_pos,
        "string_beam": string_beam,
        "charge_sheath": charge_sheath,
        "sky_bolt": sky_bolt,
        "key_corona": key_corona,
        "sparks": sparks,
    }


def build_station2_key_spark_and_formulas(scene, brass_mat, oak_mat, lightning_mat, gold_mat, cyan_mat, keyline_mat, halo_mat):
    """Beat 2: Brass Key Stand + Knuckle Spark Arc + Crisp 3D Formulas (+Q ⚡ −Q and V = k · Q / r)."""
    base = KEY_STAND_PLINTH
    # Insulated mahogany frame holding the hanging brass key cleanly at chest height
    bm_st = bmesh.new()
    bmesh.ops.create_cube(bm_st, size=1.0, matrix=Matrix.Translation((0, 0, 0.02)) @ Matrix.Diagonal((0.30, 0.20, 0.04, 1.0)))
    bmesh.ops.create_cone(bm_st, cap_ends=True, cap_tris=False, segments=12, radius1=0.016, radius2=0.013, depth=0.46, matrix=Matrix.Translation((-0.11, 0, 0.25)))
    bmesh.ops.create_cone(bm_st, cap_ends=True, cap_tris=False, segments=12, radius1=0.013, radius2=0.011, depth=0.22, matrix=Matrix.Translation((0.0, 0, 0.46)) @ Matrix.Rotation(math.radians(90.0), 4, "Y"))
    add_mesh(scene, "Beat2_InsulatorStand", bm_st, oak_mat, loc=base, smooth=True, shadow=True)

    key_pos = base + Vector((0.02, 0.0, 0.31))
    key_obj = build_brass_key(scene, "Beat2_HeroBrassKey", key_pos, brass_mat, scale=1.45)

    # Jagged electric-cyan knuckle spark arc from key toward Benjamin's approaching right hand!
    arc_bolt = build_jagged_lightning_bolt(
        scene, "Beat2_KnuckleSparkArc",
        key_pos + Vector((-0.02, -0.02, -0.03)),
        key_pos + Vector((-0.24, 0.08, 0.02)),
        lightning_mat, radius=0.012, segments=7, jitter=0.035, seed=202, add_branches=False,
    )

    # Crisp 3D Formulas on EXACT Camera DOF Plane (Y=0.20, Z=2.03m — cleanly above both heads, zero hand overlap!)
    f_charge = create_crisp_3d_text(
        scene, "Formula_Charge", "+Q  ⚡  −Q", 0.145,
        Vector((base.x, 0.20, 2.03)), gold_mat, keyline_mat, halo_mat, 1.05, 0.28,
    )
    f_volt = create_crisp_3d_text(
        scene, "Formula_Voltage", "V = k · Q / r", 0.128,
        Vector((base.x, 0.20, 2.04)), cyan_mat, keyline_mat, halo_mat, 1.16, 0.28,
    )
    return {"key_obj": key_obj, "key_pos": key_pos, "arc_bolt": arc_bolt, "f_charge": f_charge, "f_volt": f_volt}


def build_station3_leyden_jar_and_easel(scene, brass_mat, copper_mat, oak_mat, glass_mat, lightning_mat, gold_mat, cyan_mat, keyline_mat, halo_mat):
    """Beat 3: Crystal Glass Leyden Jar (shadow-bypass glass!) + Swirling Plasma + Camera-Facing +/− Slate Easel (+38 deg!)."""
    # Tripod oak lab table at LEYDEN_ANCHOR
    tbl_top_z = 1.04
    bm_t = bmesh.new()
    bmesh.ops.create_cone(bm_t, cap_ends=True, cap_tris=False, segments=24, radius1=0.25, radius2=0.26, depth=0.045, matrix=Matrix.Translation((0, 0, tbl_top_z)))
    bmesh.ops.create_cone(bm_t, cap_ends=True, cap_tris=False, segments=16, radius1=0.038, radius2=0.028, depth=tbl_top_z, matrix=Matrix.Translation((0, 0, tbl_top_z * 0.5)))
    bmesh.ops.create_cone(bm_t, cap_ends=True, cap_tris=False, segments=20, radius1=0.24, radius2=0.14, depth=0.07, matrix=Matrix.Translation((0, 0, 0.035)))
    add_mesh(scene, "Beat3_LeydenTable", bm_t, oak_mat, loc=LEYDEN_ANCHOR, smooth=True, shadow=True)

    jar_base = Vector((LEYDEN_ANCHOR.x, LEYDEN_ANCHOR.y, tbl_top_z + 0.022))

    # Outer & inner hammered brass foil jacket (lower 60% of Leyden jar)
    bm_foil = bmesh.new()
    bmesh.ops.create_cone(bm_foil, cap_ends=True, cap_tris=False, segments=28, radius1=0.112, radius2=0.114, depth=0.21, matrix=Matrix.Translation((0, 0, 0.105)))
    add_mesh(scene, "LeydenJar_BrassFoil", bm_foil, brass_mat, loc=jar_base, smooth=True, shadow=True)

    # Crystal Flint-Glass Jar Shell (with LightPath.Is Shadow Ray -> Transparent BSDF!)
    bm_g = bmesh.new()
    bmesh.ops.create_cone(bm_g, cap_ends=True, cap_tris=False, segments=28, radius1=0.116, radius2=0.116, depth=0.36, matrix=Matrix.Translation((0, 0, 0.18)))
    bmesh.ops.create_cone(bm_g, cap_ends=True, cap_tris=False, segments=24, radius1=0.072, radius2=0.068, depth=0.07, matrix=Matrix.Translation((0, 0, 0.39)))
    add_mesh(scene, "LeydenJar_CrystalGlass", bm_g, glass_mat, loc=jar_base, smooth=True, shadow=False)

    # Central Brass Collector Rod & Polished Top Terminal Sphere
    bm_rod = bmesh.new()
    bmesh.ops.create_cone(bm_rod, cap_ends=True, cap_tris=False, segments=14, radius1=0.011, radius2=0.011, depth=0.52, matrix=Matrix.Translation((0, 0, 0.31)))
    bmesh.ops.create_uvsphere(bm_rod, u_segments=20, v_segments=14, radius=0.046, matrix=Matrix.Translation((0, 0, 0.58)))
    add_mesh(scene, "LeydenJar_CollectorRod", bm_rod, copper_mat, loc=jar_base, smooth=True, shadow=True)

    # Internal Swirling Electric-Cyan Plasma Bolts inside the upper glass dome!
    plasma_root = bpy.data.objects.new("LeydenPlasma_Root", None)
    plasma_root.location = jar_base + Vector((0.0, 0.0, 0.29))
    link_obj(scene, plasma_root)
    for i in range(4):
        ang = i * (math.pi * 0.5)
        p0 = Vector((0.0, 0.0, 0.02))
        p1 = Vector((0.095 * math.cos(ang), 0.095 * math.sin(ang), -0.05 + 0.03 * (i % 2)))
        b = build_jagged_lightning_bolt(scene, f"LeydenPlasmaArc_{i}", p0, p1, lightning_mat, radius=0.0085, segments=6, jitter=0.024, seed=300 + i, add_branches=False)
        b.parent = plasma_root

    # Orbiting glowing + (amber-gold) & - (electric-cyan) charge orbs around the collector sphere!
    pos_orb_mat = make_emissive_mat("PosChargeOrbMat", (1.0, 0.72, 0.18), strength=3.0)
    neg_orb_mat = make_emissive_mat("NegChargeOrbMat", (0.22, 0.88, 1.0), strength=3.2)
    orbs = []
    for i in range(6):
        bm_o = bmesh.new()
        bmesh.ops.create_icosphere(bm_o, subdivisions=2, radius=0.018)
        o = add_mesh(scene, f"LeydenChargeOrb_{i}", bm_o, pos_orb_mat if i % 2 == 0 else neg_orb_mat, loc=jar_base + Vector((0, 0, 0.42)), smooth=True, shadow=False)
        orbs.append((o, i * (math.pi / 3.0), 0.15 + 0.025 * (i % 2), 0.34 + 0.11 * (i % 3)))

    # Camera-Facing Colonial Obsidian Slate Charge Easel (+38 deg Z rotation so dot(normal, to_cam) > +0.75!)
    easel_pos = Vector((-2.48, 0.08, 1.24))
    easel_root = bpy.data.objects.new("ChargeEasel_Root", None)
    easel_root.location = easel_pos
    easel_root.rotation_euler = Euler((0.0, 0.0, math.radians(38.0)), "XYZ")
    link_obj(scene, easel_root)

    slate_mat = make_pbr_mat("ObsidianChargeSlate", (0.015, 0.018, 0.026), rough=0.68)
    bm_sl = bmesh.new()
    bmesh.ops.create_cube(bm_sl, size=1.0, matrix=Matrix.Diagonal((0.34, 0.024, 0.46, 1.0)))
    sl = add_mesh(scene, "ChargeEasel_Slate", bm_sl, slate_mat, smooth=False, shadow=True)
    sl.parent = easel_root

    # Brass frame trim
    bm_ef = bmesh.new()
    for sx in (-0.175, 0.175):
        bmesh.ops.create_cube(bm_ef, size=1.0, matrix=Matrix.Translation((sx, 0, 0)) @ Matrix.Diagonal((0.018, 0.032, 0.48, 1.0)))
    for sz in (-0.235, 0.235):
        bmesh.ops.create_cube(bm_ef, size=1.0, matrix=Matrix.Translation((0, 0, sz)) @ Matrix.Diagonal((0.36, 0.032, 0.018, 1.0)))
    ef = add_mesh(scene, "ChargeEasel_BrassFrame", bm_ef, brass_mat, smooth=False, shadow=True)
    ef.parent = easel_root

    # Glowing + POSITIVE (top gold band) and − NEGATIVE (bottom cyan band) crisp symbols on FRONT face (-Y local!)
    font = bpy.data.fonts.load(FONT_PATH, check_existing=True)
    for label, txt, dz, mat in [
        ("EaselPlus", "+  POS", 0.10, gold_mat),
        ("EaselArrow", "↓  ⚡  ↓", 0.00, make_emissive_mat("EaselBoltEm", (0.85, 0.96, 1.0), 2.4)),
        ("EaselMinus", "−  NEG", -0.10, cyan_mat),
    ]:
        cd = bpy.data.curves.new(f"{label}_Curve", type="FONT")
        cd.body = txt
        cd.font = font
        cd.size = 0.068
        cd.align_x = "CENTER"
        cd.align_y = "CENTER"
        cd.extrude = 0.003
        obj = bpy.data.objects.new(label, cd)
        obj.location = Vector((0.0, -0.018, dz))
        obj.rotation_euler = Euler((math.radians(90.0), 0.0, 0.0), "XYZ")
        obj.data.materials.append(mat)
        obj.visible_shadow = False
        obj.parent = easel_root
        link_obj(scene, obj)

    # Live cyan energy tether from Leyden sphere to Easel center!
    tether = build_jagged_lightning_bolt(
        scene, "Beat3_LeydenToEaselArc",
        jar_base + Vector((0.04, 0.0, 0.56)),
        easel_pos + Vector((-0.14, -0.05, 0.06)),
        lightning_mat, radius=0.010, segments=7, jitter=0.035, seed=333, add_branches=False,
    )

    return {"jar_base": jar_base, "plasma_root": plasma_root, "orbs": orbs, "tether": tether}


def build_station4_steeple_and_lightning_rod(scene, copper_mat, oak_mat, lightning_mat, gold_spark_mat):
    """Beat 4: Detailed 1752 Colonial Church Steeple + Pointed Copper Lightning Rod + Grounding Wire + Thunderbolt Intercept!"""
    base = STEEPLE_PLINTH
    white_mat = make_pbr_mat("ColonialWhiteTimber", (0.76, 0.72, 0.65), rough=0.62)
    slate_mat = make_pbr_mat("ColonialRoofSlate", (0.06, 0.07, 0.10), rough=0.52)

    # Colonial church tower & steep spire
    bm_ch = bmesh.new()
    bmesh.ops.create_cube(bm_ch, size=1.0, matrix=Matrix.Translation((0, 0, 0.11)) @ Matrix.Diagonal((0.28, 0.24, 0.22, 1.0)))
    bmesh.ops.create_cube(bm_ch, size=1.0, matrix=Matrix.Translation((0, 0, 0.27)) @ Matrix.Diagonal((0.18, 0.18, 0.12, 1.0)))
    add_mesh(scene, "Beat4_ColonialChurchBase", bm_ch, white_mat, loc=base, smooth=False, shadow=True)

    bm_sp = bmesh.new()
    bmesh.ops.create_cone(bm_sp, cap_ends=True, cap_tris=False, segments=4, radius1=0.14, radius2=0.012, depth=0.34, matrix=Matrix.Translation((0, 0, 0.50)) @ Matrix.Rotation(math.radians(45.0), 4, "Z"))
    add_mesh(scene, "Beat4_ColonialSpireRoof", bm_sp, slate_mat, loc=base, smooth=False, shadow=True)

    # Gleaming Pointed Copper Lightning Rod mounted right on spire apex + external copper grounding conduit!
    rod_tip = base + Vector((0.0, 0.0, 0.94))
    bm_rod = bmesh.new()
    bmesh.ops.create_cone(bm_rod, cap_ends=True, cap_tris=False, segments=12, radius1=0.010, radius2=0.002, depth=0.30, matrix=Matrix.Translation((0, 0, 0.79)))
    # Braided copper wire running down right side into earthen grounding bar
    bmesh.ops.create_cone(bm_rod, cap_ends=True, cap_tris=False, segments=10, radius1=0.007, radius2=0.007, depth=0.72, matrix=Matrix.Translation((0.15, -0.02, 0.36)))
    bmesh.ops.create_cone(bm_rod, cap_ends=True, cap_tris=False, segments=10, radius1=0.007, radius2=0.007, depth=0.17, matrix=Matrix.Translation((0.075, -0.02, 0.68)) @ Matrix.Rotation(math.radians(90.0), 4, "Y"))
    bmesh.ops.create_cone(bm_rod, cap_ends=True, cap_tris=False, segments=16, radius1=0.055, radius2=0.055, depth=0.016, matrix=Matrix.Translation((0.15, -0.02, 0.008)))
    add_mesh(scene, "Beat4_CopperLightningRod", bm_rod, copper_mat, loc=base, smooth=True, shadow=True)

    # Blazing Thunderbolt striking straight into the pointed copper rod tip at t=17.42s!
    rod_bolt = build_jagged_lightning_bolt(
        scene, "Beat4_RodLightningBolt",
        rod_tip + Vector((0.24, 0.16, 1.45)),
        rod_tip,
        lightning_mat, radius=0.026, segments=10, jitter=0.14, seed=404, add_branches=True,
    )

    # Glowing electric-cyan current sheath running safely down the copper grounding wire!
    ground_sheath = add_open_beam_unit(scene, "Beat4_GroundingCurrentSheath", lightning_mat, r1=0.018, r2=0.018, segs=10)
    orient_beam(ground_sheath, base + Vector((0.15, -0.02, 0.01)), base + Vector((0.15, -0.02, 0.68)), 0.001)

    # Impact flash sphere + travelling current bead draining down to earth!
    bm_fl = bmesh.new()
    bmesh.ops.create_icosphere(bm_fl, subdivisions=2, radius=0.085)
    impact_flash = add_mesh(scene, "Beat4_RodImpactFlash", bm_fl, gold_spark_mat, loc=rod_tip, smooth=True, shadow=False)

    bm_bd = bmesh.new()
    bmesh.ops.create_icosphere(bm_bd, subdivisions=2, radius=0.036)
    drain_bead = add_mesh(scene, "Beat4_DrainCurrentBead", bm_bd, lightning_mat, loc=base + Vector((0.15, -0.02, 0.68)), smooth=True, shadow=False)

    return {
        "base": base,
        "rod_tip": rod_tip,
        "rod_bolt": rod_bolt,
        "ground_sheath": ground_sheath,
        "impact_flash": impact_flash,
        "drain_bead": drain_bead,
    }


def build_station5_6_electric_age_spire(scene, brass_mat, copper_mat, glass_mat, lightning_mat, gold_mat):
    """Beats 5-6: Modern Art-Deco Skyscraper Spire + Illuminated Edison Glass Lightbulb + Rotating Power-Grid Hologram!"""
    root = bpy.data.objects.new("ElectricAgeSpire_Root", None)
    root.location = Vector((SPIRE_ANCHOR.x, SPIRE_ANCHOR.y, 0.0))
    link_obj(scene, root)

    steel_mat = make_pbr_mat("SkyscraperBrushedSteel", (0.24, 0.28, 0.36), metallic=0.92, rough=0.22)
    win_em_mat = make_emissive_mat("SkyscraperWarmWindows", (1.0, 0.80, 0.36), strength=2.6)
    fil_mat = make_emissive_mat("EdisonFilamentGlow", (1.0, 0.78, 0.24), strength=3.4)

    # Stepped Art-Deco skyscraper silhouette pedestal (0.0 -> 1.18m)
    bm_tw = bmesh.new()
    bmesh.ops.create_cube(bm_tw, size=1.0, matrix=Matrix.Translation((0, 0, 0.34)) @ Matrix.Diagonal((0.30, 0.30, 0.68, 1.0)))
    bmesh.ops.create_cube(bm_tw, size=1.0, matrix=Matrix.Translation((0, 0, 0.84)) @ Matrix.Diagonal((0.22, 0.22, 0.34, 1.0)))
    bmesh.ops.create_cube(bm_tw, size=1.0, matrix=Matrix.Translation((0, 0, 1.09)) @ Matrix.Diagonal((0.14, 0.14, 0.18, 1.0)))
    tw = add_mesh(scene, "ElectricSpire_Tower", bm_tw, steel_mat, smooth=False, shadow=True)
    tw.parent = root

    # Illuminated vertical skyscraper window strips
    bm_ws = bmesh.new()
    for sx in (-0.08, 0.0, 0.08):
        for sy in (-0.152, 0.152):
            bmesh.ops.create_cube(bm_ws, size=1.0, matrix=Matrix.Translation((sx, sy, 0.38)) @ Matrix.Diagonal((0.026, 0.008, 0.56, 1.0)))
    ws = add_mesh(scene, "ElectricSpire_Windows", bm_ws, win_em_mat, smooth=False, shadow=False)
    ws.parent = root

    # Glowing Vintage Edison Glass Bulb & Filament hovering atop spire (Z = 1.46m!)
    bm_sock = bmesh.new()
    bmesh.ops.create_cone(bm_sock, cap_ends=True, cap_tris=False, segments=20, radius1=0.056, radius2=0.062, depth=0.08, matrix=Matrix.Translation((0, 0, 1.24)))
    sock = add_mesh(scene, "EdisonBulb_BrassBase", bm_sock, brass_mat, smooth=True, shadow=True)
    sock.parent = root

    bm_blb = bmesh.new()
    bmesh.ops.create_uvsphere(bm_blb, u_segments=24, v_segments=18, radius=0.145, matrix=Matrix.Translation((0, 0, 1.44)))
    blb = add_mesh(scene, "EdisonBulb_Glass", bm_blb, glass_mat, smooth=True, shadow=False)
    blb.parent = root

    # Glowing coiled tungsten filament inside glass bulb
    bm_fil = bmesh.new()
    for i in range(18):
        a0 = math.pi * (i / 18.0)
        a1 = math.pi * ((i + 1) / 18.0)
        p0 = Vector((0.058 * math.cos(a0), 0.0, 1.41 + 0.075 * math.sin(a0)))
        p1 = Vector((0.058 * math.cos(a1), 0.0, 1.41 + 0.075 * math.sin(a1)))
        mid = (p0 + p1) * 0.5
        q = (p1 - p0).normalized().to_track_quat("Z", "Y")
        bmesh.ops.create_cone(bm_fil, cap_ends=True, cap_tris=False, segments=8, radius1=0.006, radius2=0.006, depth=(p1 - p0).length * 1.15, matrix=Matrix.Translation(mid) @ q.to_matrix().to_4x4())
    fil = add_mesh(scene, "EdisonBulb_Filament", bm_fil, fil_mat, smooth=True, shadow=False)
    fil.parent = root

    # Copper Lightning Rod Crown rising above the glowing electric bulb (Z = 1.60 -> 1.88m)
    bm_cr = bmesh.new()
    bmesh.ops.create_cone(bm_cr, cap_ends=True, cap_tris=False, segments=12, radius1=0.009, radius2=0.002, depth=0.28, matrix=Matrix.Translation((0, 0, 1.72)))
    cr = add_mesh(scene, "ElectricSpire_RodCrown", bm_cr, copper_mat, smooth=True, shadow=False)
    cr.parent = root

    # Rotating Holographic Electric-Grid Rings orbiting the bulb (strictly <= 0.24m radius so zero hand clipping!)
    rings_root = bpy.data.objects.new("ElectricGridRings_Root", None)
    rings_root.location = Vector((0.0, 0.0, 1.44))
    rings_root.parent = root
    link_obj(scene, rings_root)

    for idx, (rad, tilt) in enumerate([(0.22, 22.0), (0.24, -26.0)]):
        bm_r = bmesh.new()
        segs = 32
        for i in range(segs):
            a0 = 2.0 * math.pi * i / segs
            a1 = 2.0 * math.pi * (i + 1) / segs
            p0 = Vector((rad * math.cos(a0), rad * math.sin(a0), 0.0))
            p1 = Vector((rad * math.cos(a1), rad * math.sin(a1), 0.0))
            mid = (p0 + p1) * 0.5
            q = (p1 - p0).normalized().to_track_quat("Z", "Y")
            bmesh.ops.create_cone(bm_r, cap_ends=False, cap_tris=False, segments=6, radius1=0.0055, radius2=0.0055, depth=(p1 - p0).length * 1.05, matrix=Matrix.Translation(mid) @ q.to_matrix().to_4x4())
        ring_obj = add_mesh(scene, f"ElectricGridRing_{idx}", bm_r, lightning_mat if idx == 0 else gold_mat, rot=(math.radians(tilt), 0.0, 0.0), smooth=True, shadow=False)
        ring_obj.parent = rings_root

    # Warm bulb point glow (illuminates Benjamin & William's faces in Beats 5-6!)
    bulb_ld = bpy.data.lights.new("EdisonBulbGlowLight", type="POINT")
    bulb_ld.energy = 0.0
    bulb_ld.color = (1.0, 0.80, 0.38)
    bulb_ld.shadow_soft_size = 0.24
    bulb_light = bpy.data.objects.new("EdisonBulbGlowLight", bulb_ld)
    bulb_light.location = Vector((0.0, -0.10, 1.44))
    bulb_light.parent = root
    link_obj(scene, bulb_light)

    return {"root": root, "rings_root": rings_root, "bulb_light": bulb_light}


def build_beat6_sky_monument(scene, gold_mat, cyan_mat, keyline_mat, halo_mat, brass_mat):
    """AGENTS.md Section 2: 2-Tier Sky Monument cleanly in open sky (Y=0.24, Z=2.52m)."""
    root = bpy.data.objects.new("FranklinTitle3D_Root", None)
    root.location = Vector((0.55, 0.24, 2.52))
    link_obj(scene, root)

    font = bpy.data.fonts.load(FONT_PATH, check_existing=True)

    def _tier(cname: str, body: str, sz: float, dz: float, mat):
        for suffix, ext, bev, m, dy in [("Face", 0.0048, 0.0006, mat, 0.0), ("Key", 0.0044, 0.0018, keyline_mat, 0.0065)]:
            cd = bpy.data.curves.new(f"{cname}_{suffix}_Curve", type="FONT")
            cd.body = body
            cd.font = font
            cd.size = sz
            cd.align_x = "CENTER"
            cd.align_y = "CENTER"
            cd.extrude = ext
            cd.bevel_depth = bev
            cd.bevel_resolution = 2
            obj = bpy.data.objects.new(f"{cname}_{suffix}", cd)
            obj.location = Vector((0.0, dy, dz))
            obj.rotation_euler = Euler((math.radians(90.0), 0.0, 0.0), "XYZ")
            obj.data.materials.append(m)
            obj.visible_shadow = False
            obj.parent = root
            link_obj(scene, obj)

    _tier("TitleMain", "BENJAMIN FRANKLIN", 0.132, 0.085, gold_mat)
    _tier("TitleSub", "LIGHTNING = ELECTRICITY", 0.072, -0.082, cyan_mat)

    bm_rule = bmesh.new()
    bmesh.ops.create_cube(bm_rule, size=1.0, matrix=Matrix.Translation((0.0, 0.0, 0.0)) @ Matrix.Diagonal((1.35, 0.006, 0.008, 1.0)))
    rule = add_mesh(scene, "TitleHairlineRule", bm_rule, brass_mat, smooth=False, shadow=False)
    rule.parent = root

    bm_h = bmesh.new()
    bmesh.ops.create_grid(bm_h, x_segments=1, y_segments=1, size=0.5, matrix=Matrix.Diagonal((1.95, 0.44, 1.0, 1.0)))
    halo = add_mesh(scene, "TitleSkyVeilHalo", bm_h, halo_mat, loc=(0.0, 0.018, 0.0), rot=(math.radians(90.0), 0.0, 0.0), smooth=False, shadow=False)
    halo.parent = root
    return root


# ============================================================================
# 6-BEAT CAMERA CHOREOGRAPHY (EXACT 1:1 MATCH WITH src/verify_framing.py!)
# ============================================================================
def compute_camera(t: float) -> tuple[Vector, Vector, float, float]:
    if t < 4.5:
        u = clamp01(t / 4.5)
        pos = bezier_quad(Vector((-0.82, -1.86, 1.32)), Vector((-0.79, -1.78, 1.36)), Vector((-0.76, -1.70, 1.38)), u)
        tgt = Vector((-0.79, 0.24, 1.46)).lerp(Vector((-0.78, 0.22, 1.38)), u)
        return pos, tgt, lerp(36.0, 38.0, u), 0.0
    if t < 9.8:
        pan_u = ease_out_quint(clamp01((t - 6.95) / 1.1))
        pos = Vector((0.60, -2.18, 1.42)).lerp(Vector((0.52, -2.10, 1.42)), pan_u)
        tgt = Vector((0.57, 0.28, 1.32)).lerp(Vector((0.54, 0.30, 1.32)), pan_u)
        return pos, tgt, lerp(34.5, 34.0, pan_u), 0.0
    if t < 15.5:
        u = clamp01((t - 9.8) / 5.7)
        pos = bezier_quad(Vector((-2.52, -1.78, 1.40)), Vector((-2.49, -1.68, 1.41)), Vector((-2.46, -1.62, 1.42)), u)
        tgt = Vector((-2.50, 0.18, 1.32)).lerp(Vector((-2.48, 0.20, 1.36)), smoothstep(10.6, 13.0, t))
        return pos, tgt, lerp(37.5, 39.0, u), 0.0
    if t < 20.5:
        u = clamp01((t - 15.5) / 5.0)
        pos = bezier_quad(Vector((2.60, -1.92, 1.38)), Vector((2.64, -1.86, 1.39)), Vector((2.68, -1.82, 1.40)), u)
        tgt = Vector((2.60, 0.22, 1.34))
        return pos, tgt, lerp(34.5, 36.0, u), 3.6
    if t < 25.5:
        u = clamp01((t - 20.5) / 5.0)
        pos = bezier_quad(Vector((0.26, -1.94, 1.36)), Vector((0.30, -1.88, 1.44)), Vector((0.34, -1.84, 1.50)), u)
        tgt = Vector((0.30, 0.24, 1.44)).lerp(Vector((0.32, 0.26, 1.52)), u)
        return pos, tgt, lerp(35.0, 36.0, u), 0.0
    u = clamp01((t - 25.5) / 4.5)
    pos = bezier_quad(Vector((0.55, -2.55, 1.52)), Vector((0.55, -2.72, 1.58)), Vector((0.55, -2.88, 1.62)), u)
    tgt = Vector((0.55, 0.30, 1.54)).lerp(Vector((0.55, 0.28, 1.52)), u)
    return pos, tgt, lerp(32.0, 30.5, u), 0.0


# ============================================================================
# MAIN SCENE BUILD & RENDER ENTRYPOINT
# ============================================================================
def configure_cycles(scene, args):
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    scene.cycles.samples = args.samples
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.035
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    scene.cycles.denoising_input_passes = "RGB_ALBEDO"
    scene.cycles.max_bounces = 6
    scene.cycles.diffuse_bounces = 1
    scene.cycles.glossy_bounces = 3
    scene.cycles.transmission_bounces = 6
    scene.cycles.transparent_max_bounces = 10  # AGENTS.md Section 3 mandatory >= 10
    scene.cycles.caustics_reflective = False
    scene.cycles.caustics_refractive = False

    prefs = bpy.context.preferences.addons["cycles"].preferences
    for backend in (args.device, "OPTIX", "CUDA"):
        try:
            prefs.compute_device_type = backend
            prefs.get_devices()
            gpus = [d for d in prefs.devices if d.type != "CPU"]
            if gpus:
                for d in prefs.devices:
                    d.use = (d.type != "CPU")
                print(f"[Cycles GPU] Active backend: {backend} ({len(gpus)} GPU(s))")
                break
        except Exception:
            continue

    scene.render.resolution_x = RES_X
    scene.render.resolution_y = RES_Y
    scene.render.resolution_percentage = args.scale
    scene.render.fps = FPS
    scene.frame_start = 1
    scene.frame_end = TOTAL_FRAMES
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 95

    scene.view_settings.view_transform = "AgX"
    try:
        scene.view_settings.look = "AgX - Punchy"
    except Exception:
        pass
    scene.view_settings.exposure = 0.15


def build_and_render(args):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    configure_cycles(scene, args)
    manifest = load_voice_manifest()

    # 1. Build V10 Photoreal 1752 Stormy Philadelphia -> Electric-Age Cosmos World
    world_handles = build_franklin_world(scene)

    # 2. Shared Hero Materials (AGENTS.md V10)
    brass_mat = make_pbr_mat("HeroPolishedBrass", (0.86, 0.64, 0.22), metallic=0.96, rough=0.20)
    copper_mat = make_pbr_mat("HeroBurnishedCopper", (0.88, 0.42, 0.20), metallic=0.96, rough=0.22)
    oak_mat = make_pbr_mat("HeroDarkMahogany", (0.09, 0.045, 0.022), metallic=0.0, rough=0.42, coat=0.25)
    glass_mat = make_crystal_glass_mat("HeroFlintGlass", (0.90, 0.97, 1.0), ior=1.52, rough=0.025)
    lightning_mat = make_additive_lightning_mat("VolumetricLightningCyan", (0.48, 0.90, 1.0), strength=3.6)
    gold_spark_mat = make_additive_lightning_mat("VolumetricSparkGold", (1.0, 0.78, 0.24), strength=3.2)
    gold_text_mat = make_crisp_formula_mat("FormulaGold2Zone", (1.0, 0.80, 0.26), strength=1.75)
    cyan_text_mat = make_crisp_formula_mat("FormulaCyan2Zone", (0.42, 0.92, 1.0), strength=1.80)
    keyline_mat = make_text_keyline_mat()
    halo_mat = make_formula_halo_mat(opacity=0.78)

    # 3. Build 6 Hero Physics Stations
    st1 = build_station1_kite_and_key(scene, brass_mat, oak_mat, lightning_mat, gold_spark_mat)
    st2 = build_station2_key_spark_and_formulas(scene, brass_mat, oak_mat, lightning_mat, gold_text_mat, cyan_text_mat, keyline_mat, halo_mat)
    st3 = build_station3_leyden_jar_and_easel(scene, brass_mat, copper_mat, oak_mat, glass_mat, lightning_mat, gold_text_mat, cyan_text_mat, keyline_mat, halo_mat)
    st4 = build_station4_steeple_and_lightning_rod(scene, copper_mat, oak_mat, lightning_mat, gold_spark_mat)
    st56 = build_station5_6_electric_age_spire(scene, brass_mat, copper_mat, glass_mat, lightning_mat, gold_text_mat)
    title_root = build_beat6_sky_monument(scene, gold_text_mat, cyan_text_mat, keyline_mat, halo_mat, brass_mat)

    # 4. Build MPFB2 Photoreal Cast: Benjamin Franklin (with 3D Brass Spectacles!) & William Franklin
    franklin_actor = None
    william_actor = None
    try:
        franklin_actor = create_realistic_scientist(
            name="BenjaminFranklin",
            floor_z=FLOOR_Z,
            start_xy=(-1.06, 0.36),
            yaw_deg=26.0,
            cfg={
                "age": 0.66,
                "muscle": 0.48,
                "weight": 0.56,
                "height": 0.59,
                "target_height_m": 1.79,
                "skin_assets": ["middleage_caucasian_male.mhmat"],
                "iris_major_rgb": (0.26, 0.50, 0.68),
                "iris_minor_rgb": (0.12, 0.24, 0.38),
                "eyebrow_assets": ["eyebrow002.mhclo", "eyebrow001.mhclo"],
                "hair_assets": ["culturalibre_hair_01.mhclo"],
                "hair_gamma_lift": 0.32,
                "hair_value_boost": 1.32,
                "hair_tint_rgb": (0.84, 0.80, 0.74),
                "hair_tint_fac": 0.62,
                "brow_tint_rgb": (0.48, 0.44, 0.40),
                "brow_tint_fac": 0.50,
                "silver_hair": False,
                "silver_hair_main": False,
                "coat_assets": ["mindfront_lusekofta.mhclo", "elvs_male_boho_top1.mhclo"],
                "coat_gamma_lift": 0.56,
                "coat_sat_override": 0.16,
                "coat_value_boost": 1.02,
                "coat_tint_rgb": (0.26, 0.14, 0.08),  # Distinguished colonial walnut-velvet coat
                "coat_tint_fac": 0.90,
                "coat_roughness": 0.74,
                "coat_sheen": 0.66,
                "coat_auto_metal_map": True,
                "pants_assets": ["mindfront_male_trousers_2.mhclo"],
                "pants_tint_rgb": (0.14, 0.12, 0.11),
                "pants_tint_fac": 0.72,
                "shoe_assets": ["toigo_ankle_boots_male.mhclo"],
                "add_cravat": False,
                "add_scholar_cloak": False,
            },
            brass_mat=brass_mat,
        )
        attach_franklin_spectacles(scene, franklin_actor["rig"], brass_mat, glass_mat)

        william_actor = create_realistic_scientist(
            name="WilliamFranklin",
            floor_z=FLOOR_Z,
            start_xy=(1.12, 0.46),
            yaw_deg=-26.0,
            cfg={
                "age": 0.56,
                "muscle": 0.56,
                "weight": 0.46,
                "height": 0.58,
                "target_height_m": 1.78,
                "skin_assets": ["middleage_caucasian_male.mhmat"],
                "iris_major_rgb": (0.58, 0.36, 0.14),
                "iris_minor_rgb": (0.28, 0.16, 0.06),
                "eyebrow_assets": ["eyebrow003.mhclo", "eyebrow002.mhclo"],
                "hair_assets": ["short04.mhclo"],
                "hair_gamma_lift": 0.66,
                "hair_value_boost": 1.05,
                "hair_tint_rgb": (0.40, 0.24, 0.14),
                "hair_tint_fac": 0.62,
                "brow_tint_rgb": (0.28, 0.18, 0.10),
                "brow_tint_fac": 0.50,
                "silver_hair": False,
                "coat_assets": ["donitz_monk_robe.mhclo"],
                "coat_gamma_lift": 0.44,
                "coat_sat_override": 0.14,
                "coat_value_boost": 1.05,
                "coat_tint_rgb": (0.07, 0.16, 0.38),  # Colonial midnight-indigo coat
                "coat_tint_fac": 0.92,
                "coat_roughness": 0.76,
                "coat_sheen": 0.70,
                "shoe_assets": ["punkduck_medieval_boots.mhclo"],
                "add_cravat": False,
                "add_scholar_cloak": False,
            },
            brass_mat=brass_mat,
        )
    except Exception as err:
        print(f"[MPFB2 Warning] Skipping human cast: {err}")

    # 5. Cinema Portrait Camera (9:16, Horizontal Sensor Fit 36mm, Crisp DOF f/5.6)
    cam_data = bpy.data.cameras.new("FranklinCam")
    cam_data.sensor_fit = "HORIZONTAL"
    cam_data.sensor_width = 36.0
    cam_data.clip_start = 0.05
    cam_data.clip_end = 120.0
    cam_data.dof.use_dof = True
    cam_data.dof.aperture_fstop = 5.6
    cam_obj = bpy.data.objects.new("FranklinCam", cam_data)
    link_obj(scene, cam_obj)
    scene.camera = cam_obj

    # 6. Keyframe Every Frame (only within needed range or every 2 frames for fast scene build!)
    step = 2
    key_frames = sorted(set(list(range(1, TOTAL_FRAMES + 1, step)) + [1, TOTAL_FRAMES]))

    for f in key_frames:
        t = (f - 1) / float(FPS)
        cpos, ctgt, lens, roll_deg = compute_camera(t)
        cam_obj.location = cpos
        q = (ctgt - cpos).normalized().to_track_quat("-Z", "Y")
        if abs(roll_deg) > 1e-3:
            q = q @ Euler((0.0, 0.0, math.radians(roll_deg)), "XYZ").to_quaternion()
        cam_obj.rotation_mode = "QUATERNION"
        cam_obj.rotation_quaternion = q
        cam_data.lens = lens
        cam_data.dof.focus_distance = (ctgt - cpos).length
        cam_obj.keyframe_insert(data_path="location", frame=f)
        cam_obj.keyframe_insert(data_path="rotation_quaternion", frame=f)
        cam_data.keyframe_insert(data_path="lens", frame=f)
        cam_data.dof.keyframe_insert(data_path="focus_distance", frame=f)

        animate_franklin_world(world_handles, f, t, focus_x=ctgt.x)

        # --- Station 1 Animation (Beat 1: Stormy Kite & Lightning Strike at t=2.08s) ---
        k_sway_x = 0.075 * math.sin(t * 2.8)
        k_sway_z = 0.055 * math.cos(t * 2.1)
        st1["kite_root"].location = KITE_POS + Vector((k_sway_x, 0.0, k_sway_z))
        st1["kite_root"].rotation_euler = Euler((math.radians(-14.0), math.radians(10.0 * math.sin(t * 2.4)), math.radians(8.0 * math.cos(t * 1.9))), "XYZ")
        st1["kite_root"].keyframe_insert(data_path="location", frame=f)
        st1["kite_root"].keyframe_insert(data_path="rotation_euler", frame=f)

        b1_vis = 1.0 if t < 4.55 else 0.0001
        bolt1_pulse = (smoothstep(1.98, 2.08, t) * (1.0 - smoothstep(2.45, 2.95, t)) + 0.65 * smoothstep(3.15, 3.22, t) * (1.0 - smoothstep(3.48, 3.80, t))) * b1_vis
        bs1 = max(0.0001, bolt1_pulse)
        st1["sky_bolt"].scale = (bs1, bs1, bs1)
        st1["sky_bolt"].keyframe_insert(data_path="scale", frame=f)
        orient_beam(st1["charge_sheath"], st1["key_pos"] + Vector((0, 0, 0.06)), st1["kite_root"].location + Vector((0, 0, 0.42)), max(0.0001, bolt1_pulse * 1.35), frame=f)
        cor_s = max(0.0001, bolt1_pulse * (1.0 + 0.25 * math.sin(t * 42.0)))
        st1["key_corona"].scale = (cor_s, cor_s, cor_s)
        st1["key_corona"].keyframe_insert(data_path="scale", frame=f)
        for sp, d_v, length in st1["sparks"]:
            orient_beam(sp, st1["key_pos"], st1["key_pos"] + d_v * (length * (0.4 + 0.8 * bolt1_pulse)), max(0.0001, bolt1_pulse), frame=f)

        # --- Station 2 Animation (Beat 2: Knuckle Spark at t=7.02s & Crisp Formulas) ---
        spark2 = smoothstep(6.92, 7.02, t) * (1.0 - smoothstep(7.55, 8.20, t)) + 0.55 * smoothstep(8.45, 8.55, t) * (1.0 - smoothstep(8.95, 9.45, t))
        s2 = max(0.0001, spark2)
        st2["arc_bolt"].scale = (s2, s2, s2)
        st2["arc_bolt"].keyframe_insert(data_path="scale", frame=f)

        f1_s = max(0.0001, smoothstep(4.75, 5.15, t) * (1.0 - smoothstep(6.90, 7.15, t)))
        f2_s = max(0.0001, smoothstep(7.10, 7.45, t) * (1.0 - smoothstep(9.55, 9.80, t)))
        st2["f_charge"].scale = (f1_s, f1_s, f1_s)
        st2["f_volt"].scale = (f2_s, f2_s, f2_s)
        st2["f_charge"].keyframe_insert(data_path="scale", frame=f)
        st2["f_volt"].keyframe_insert(data_path="scale", frame=f)

        # --- Station 3 Animation (Beat 3: Leyden Jar Swirling Plasma & Charge Orbs) ---
        b3_on = smoothstep(9.9, 10.6, t) * (1.0 - smoothstep(15.2, 15.6, t))
        st3["plasma_root"].rotation_euler = Euler((0.0, 0.0, t * 4.8), "XYZ")
        ps3 = max(0.0001, b3_on * (0.85 + 0.25 * math.sin(t * 28.0)))
        st3["plasma_root"].scale = (ps3, ps3, ps3)
        st3["plasma_root"].keyframe_insert(data_path="rotation_euler", frame=f)
        st3["plasma_root"].keyframe_insert(data_path="scale", frame=f)

        teth_s = max(0.0001, smoothstep(10.8, 11.4, t) * (1.0 - smoothstep(15.1, 15.5, t)) * (0.75 + 0.35 * math.sin(t * 36.0)))
        st3["tether"].scale = (teth_s, teth_s, teth_s)
        st3["tether"].keyframe_insert(data_path="scale", frame=f)

        for orb, ph, rad, z_off in st3["orbs"]:
            ang = ph + t * 2.6
            orb.location = st3["jar_base"] + Vector((rad * math.cos(ang), rad * math.sin(ang), z_off + 0.03 * math.sin(t * 3.5 + ph)))
            os3 = max(0.0001, b3_on)
            orb.scale = (os3, os3, os3)
            orb.keyframe_insert(data_path="location", frame=f)
            orb.keyframe_insert(data_path="scale", frame=f)

        # --- Station 4 Animation (Beat 4: Steeple Lightning Bolt Intercept at t=17.42s!) ---
        b4_bolt = smoothstep(17.34, 17.42, t) * (1.0 - smoothstep(18.05, 18.65, t)) + 0.55 * smoothstep(18.95, 19.04, t) * (1.0 - smoothstep(19.45, 19.95, t))
        s4 = max(0.0001, b4_bolt)
        st4["rod_bolt"].scale = (s4, s4, s4)
        st4["rod_bolt"].keyframe_insert(data_path="scale", frame=f)
        st4["impact_flash"].scale = (s4 * 1.25, s4 * 1.25, s4 * 1.25)
        st4["impact_flash"].keyframe_insert(data_path="scale", frame=f)

        drain_u = clamp01((t - 17.45) / 1.15)
        drain_on = smoothstep(17.40, 17.48, t) * (1.0 - smoothstep(19.50, 20.15, t))
        orient_beam(st4["ground_sheath"], st4["base"] + Vector((0.15, -0.02, 0.01)), st4["base"] + Vector((0.15, -0.02, 0.68)), max(0.0001, drain_on * 1.2), frame=f)
        st4["drain_bead"].location = st4["base"] + Vector((0.15, -0.02, lerp(0.68, 0.02, drain_u)))
        bd_s = max(0.0001, drain_on * (1.0 - 0.5 * drain_u))
        st4["drain_bead"].scale = (bd_s, bd_s, bd_s)
        st4["drain_bead"].keyframe_insert(data_path="location", frame=f)
        st4["drain_bead"].keyframe_insert(data_path="scale", frame=f)

        # --- Stations 5-6 Animation (Electric Age Spire & Monument Title) ---
        spire_vis = smoothstep(20.4, 21.1, t)
        sp_s = max(0.0001, spire_vis)
        spire_x = lerp(SPIRE_ANCHOR.x, 0.55, smoothstep(25.3, 25.8, t))
        st56["root"].location = Vector((spire_x, SPIRE_ANCHOR.y, 0.0))
        st56["root"].scale = (sp_s, sp_s, sp_s)
        st56["root"].keyframe_insert(data_path="location", frame=f)
        st56["root"].keyframe_insert(data_path="scale", frame=f)
        st56["rings_root"].rotation_euler = Euler((0.0, 0.0, t * 1.45), "XYZ")
        st56["rings_root"].keyframe_insert(data_path="rotation_euler", frame=f)
        st56["bulb_light"].data.energy = spire_vis * (68.0 + 14.0 * math.sin(t * 7.5))
        st56["bulb_light"].data.keyframe_insert(data_path="energy", frame=f)

        t6_s = max(0.0001, smoothstep(25.8, 26.6, t))
        title_root.scale = (t6_s, t6_s, t6_s)
        title_root.keyframe_insert(data_path="scale", frame=f)

        # --- Cast Placement, Expressive Acting & Zero-Clipping Choreography ---
        if franklin_actor is not None:
            fr_rig = franklin_actor["rig"]
            f_lip, f_nar = sample_lip(manifest, "franklin", t)
            if t < 4.5:
                fx, fy, fyaw = -1.06, 0.36, 26.0
                eye_yaw, eye_pitch, smile, brow = 10.0, -10.0, 0.25, 0.35
                apply_arm_with_clavicle(fr_rig, "R", (-52.0, 12.0, -14.0), (-36.0, 0.0, 10.0), frame=f)
                apply_arm_with_clavicle(fr_rig, "L", (-24.0, -10.0, 8.0), (-26.0, 0.0, -8.0), frame=f)
                apply_hand_gesture(fr_rig, "R", "point", frame=f)
                apply_hand_gesture(fr_rig, "L", "relaxed", frame=f)
            elif t < 9.8:
                fx, fy, fyaw = -0.02, 0.46, 36.0
                reach = smoothstep(6.65, 7.05, t) * (1.0 - smoothstep(7.80, 8.50, t))
                eye_yaw, eye_pitch, smile, brow = 12.0, 2.0, 0.35, 0.25
                apply_arm_with_clavicle(fr_rig, "R", (lerp(-24.0, -48.0, reach), 14.0, lerp(-12.0, -24.0, reach)), (lerp(-28.0, -22.0, reach), 0.0, 12.0), frame=f)
                apply_arm_with_clavicle(fr_rig, "L", (-14.0, -12.0, 8.0), (-22.0, 0.0, -6.0), frame=f)
                apply_hand_gesture(fr_rig, "R", "point" if reach > 0.3 else "present", frame=f)
                apply_hand_gesture(fr_rig, "L", "relaxed", frame=f)
            elif t < 15.5:
                fx, fy, fyaw = -2.04, 0.44, -34.0
                eye_yaw, eye_pitch, smile, brow = -11.0, 4.0, 0.40, 0.20
                apply_arm_with_clavicle(fr_rig, "L", (-32.0, -14.0, 16.0), (-34.0, 0.0, -10.0), frame=f)
                apply_arm_with_clavicle(fr_rig, "R", (-14.0, 12.0, -8.0), (-20.0, 0.0, 6.0), frame=f)
                apply_hand_gesture(fr_rig, "L", "present", frame=f)
                apply_hand_gesture(fr_rig, "R", "relaxed", frame=f)
            elif t < 20.5:
                fx, fy, fyaw = -0.10, 0.50, 22.0  # Parked off-camera cleanly for Beat 4!
                eye_yaw, eye_pitch, smile, brow = 0.0, 0.0, 0.2, 0.0
            elif t < 25.5:
                fx, fy, fyaw = -0.10, 0.50, 26.0
                eye_yaw, eye_pitch, smile, brow = 10.0, -4.0, 0.48, 0.30
                # Safe >= 0.18m hand clearance from Electric Spire (AGENTS.md Section 4!)
                apply_arm_with_clavicle(fr_rig, "R", (-24.0, 10.0, -10.0), (-30.0, 0.0, 8.0), frame=f)
                apply_arm_with_clavicle(fr_rig, "L", (-14.0, -10.0, 6.0), (-20.0, 0.0, -6.0), frame=f)
                apply_hand_gesture(fr_rig, "R", "present", frame=f)
                apply_hand_gesture(fr_rig, "L", "relaxed", frame=f)
            else:
                fx, fy, fyaw = -0.14, 0.48, 22.0
                eye_yaw, eye_pitch, smile, brow = 6.0, -3.0, 0.55, 0.25
                apply_arm_with_clavicle(fr_rig, "R", (-20.0, 10.0, -8.0), (-26.0, 0.0, 8.0), frame=f)
                apply_arm_with_clavicle(fr_rig, "L", (-12.0, -10.0, 6.0), (-18.0, 0.0, -6.0), frame=f)
                apply_hand_gesture(fr_rig, "R", "present", frame=f)
                apply_hand_gesture(fr_rig, "L", "relaxed", frame=f)

            fr_rig.location = Vector((fx, fy, franklin_actor["base_z"]))
            fr_rig.rotation_euler = Euler((0.0, 0.0, math.radians(fyaw)), "XYZ")
            fr_rig.keyframe_insert(data_path="location", frame=f)
            fr_rig.keyframe_insert(data_path="rotation_euler", frame=f)
            set_bone_char_rot(fr_rig, "neck01", eye_pitch * 0.35, 0.0, eye_yaw * 0.35, frame=f)
            set_bone_char_rot(fr_rig, "head", eye_pitch * 0.55, 0.0, eye_yaw * 0.55, frame=f)
            apply_natural_stance(fr_rig, frame=f, weight_shift=0.35 * math.sin(t * 0.55), breath_phase=t * 1.45, knee_bend=0.0)
            apply_facial_acting(
                fr_rig, t, frame=f,
                jaw_open_deg=f_lip * 8.8,
                brow_lift=brow, smile=smile,
                blink_period=3.4, blink_phase=0.5,
                eye_yaw_deg=eye_yaw, eye_pitch_deg=eye_pitch,
                lip_narrow=f_nar,
            )

        if william_actor is not None:
            wl_rig = william_actor["rig"]
            w_lip, w_nar = sample_lip(manifest, "william", t)
            shock4 = smoothstep(17.42, 17.58, t) * (1.0 - smoothstep(19.30, 20.10, t))
            if t < 4.5:
                wx, wy, wyaw = 1.12, 0.46, -34.0  # Off-camera Beat 1
                eye_yaw, eye_pitch, smile, brow = -8.0, 0.0, 0.1, 0.1
            elif t < 9.8:
                wx, wy, wyaw = 1.12, 0.46, -34.0
                eye_yaw, eye_pitch, smile, brow = -12.0, 0.0, -0.15, 0.55
                apply_arm_with_clavicle(wl_rig, "L", (-36.0, -12.0, 14.0), (-42.0, 0.0, -10.0), frame=f)
                apply_arm_with_clavicle(wl_rig, "R", (-18.0, 10.0, -8.0), (-26.0, 0.0, 8.0), frame=f)
                apply_hand_gesture(wl_rig, "L", "shock", frame=f)
                apply_hand_gesture(wl_rig, "R", "relaxed", frame=f)
            elif t < 15.5:
                wx, wy, wyaw = 2.30, 0.48, 30.0  # Off-camera Beat 3
                eye_yaw, eye_pitch, smile, brow = 8.0, 0.0, 0.1, 0.0
            elif t < 20.5:
                # Beat 4: Viral shock recoil from copper lightning rod intercept!
                wx = lerp(2.30, 2.22, shock4)
                wy = lerp(0.46, 0.54, shock4)
                wyaw = 32.0
                eye_yaw, eye_pitch, smile, brow = 11.0, -4.0, -0.10, 0.72 * shock4 + 0.20
                apply_arm_with_clavicle(wl_rig, "R", (lerp(-22.0, -56.0, shock4), 16.0, -14.0), (lerp(-28.0, -54.0, shock4), 0.0, 12.0), frame=f)
                apply_arm_with_clavicle(wl_rig, "L", (lerp(-18.0, -52.0, shock4), -16.0, 14.0), (lerp(-24.0, -52.0, shock4), 0.0, -12.0), frame=f)
                apply_hand_gesture(wl_rig, "R", "shock" if shock4 > 0.25 else "relaxed", frame=f)
                apply_hand_gesture(wl_rig, "L", "shock" if shock4 > 0.25 else "relaxed", frame=f)
                set_bone_char_rot(wl_rig, "spine02", -10.0 * shock4, 0.0, 0.0, frame=f)
            elif t < 25.5:
                wx, wy, wyaw = 1.24, 0.48, -22.0  # Off-camera Beat 5
                eye_yaw, eye_pitch, smile, brow = -8.0, 0.0, 0.35, 0.1
            else:
                wx, wy, wyaw = 1.24, 0.48, -22.0
                eye_yaw, eye_pitch, smile, brow = -6.0, -3.0, 0.55, 0.25
                apply_arm_with_clavicle(wl_rig, "L", (-20.0, -10.0, 8.0), (-26.0, 0.0, -8.0), frame=f)
                apply_arm_with_clavicle(wl_rig, "R", (-12.0, 10.0, -6.0), (-18.0, 0.0, 6.0), frame=f)
                apply_hand_gesture(wl_rig, "L", "present", frame=f)
                apply_hand_gesture(wl_rig, "R", "relaxed", frame=f)

            wl_rig.location = Vector((wx, wy, william_actor["base_z"]))
            wl_rig.rotation_euler = Euler((0.0, 0.0, math.radians(wyaw)), "XYZ")
            wl_rig.keyframe_insert(data_path="location", frame=f)
            wl_rig.keyframe_insert(data_path="rotation_euler", frame=f)
            set_bone_char_rot(wl_rig, "neck01", eye_pitch * 0.35, 0.0, eye_yaw * 0.35, frame=f)
            set_bone_char_rot(wl_rig, "head", eye_pitch * 0.55, 0.0, eye_yaw * 0.55, frame=f)
            apply_natural_stance(wl_rig, frame=f, weight_shift=-0.35 * math.cos(t * 0.50), breath_phase=t * 1.55 + 0.8, knee_bend=0.65 * shock4)
            jaw_w = max(w_lip * 9.0, 10.4 * shock4)  # AGENTS.md natural jaw cap <= 14 deg!
            apply_facial_acting(
                wl_rig, t, frame=f,
                jaw_open_deg=jaw_w,
                brow_lift=brow, smile=smile,
                blink_period=3.1, blink_phase=1.4,
                eye_yaw_deg=eye_yaw, eye_pitch_deg=eye_pitch,
                lip_narrow=w_nar,
            )

    # 7. Render Requested Frame Range
    out_dir = Path(args.frames_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.preview:
        frames_to_render = [54, 174, 306, 424, 558, 678]
    else:
        frames_to_render = list(range(max(1, args.start_frame), min(TOTAL_FRAMES, args.end_frame) + 1))

    for f in frames_to_render:
        scene.frame_set(f)
        scene.render.filepath = str(out_dir / f"frame_{f:04d}.jpg")
        bpy.ops.render.render(write_still=True)

    print(f"[Franklin V10] Rendered {len(frames_to_render)} frame(s) into {out_dir}")


if __name__ == "__main__":
    build_and_render(parse_args())
