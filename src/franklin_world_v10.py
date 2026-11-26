"""
V10 Cinema Photoreal 1752 Stormy Philadelphia Meadow & Colonial Terrace -> Starry Electric-Age Cosmos
Environment Module for Scientist #10: Benjamin Franklin (Lightning Kite, Leyden Jar & Copper Lightning Rod).

100% AGENTS.md V10 Compliant:
  - Rain-glazed colonial cobblestone courtyard & wet meadow grass reflecting electric-cyan lightning & warm lantern amber
  - Animated storm-indigo thundercloud sky with live lightning-flash strobes (t=2.08s, t=7.02s, t=17.42s)
    transitioning smoothly into a crisp starry clearing twilight sky (Beats 5-6) with 160 3D stars & Crescent Moon
  - Colonial split-rail timber fence, distant 1752 Philadelphia brick manor silhouette with warm glowing casements,
    and flickering wrought-iron colonial pier lantern
  - 3 carved stone & dark-oak laboratory plinths with antique-brass inlay rings + open terrace anchors
  - Hollywood Chiaroscuro Lighting Rig with AGENTS.md 0.42m Softbox AREA Eye Catchlight (Z=1.62m)
"""
from __future__ import annotations

import math
import random

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

# ============================================================================
# 1. PUBLIC WORLD CONSTANTS & EXACT V10 ANCHOR COORDINATES (6-BEAT ISOLATION)
# ============================================================================
FLOOR_Z = 0.0
KITE_POS = Vector((-0.44, 0.28, 2.38))
KITE_KEY_PLINTH = Vector((-0.52, 0.12, 0.88))
KEY_STAND_PLINTH = Vector((0.55, 0.08, 0.90))
LEYDEN_ANCHOR = Vector((-2.85, 0.06, 0.0))
STEEPLE_PLINTH = Vector((2.88, 0.08, 0.90))
SPIRE_ANCHOR = Vector((0.64, 0.14, 0.0))
CRESCENT_MOON_POS = Vector((5.20, 19.50, 8.90))


def clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def smoothstep(e0: float, e1: float, x: float) -> float:
    u = clamp01((x - e0) / max(1e-6, e1 - e0))
    return u * u * (3.0 - 2.0 * u)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def set_bsdf(bsdf, name: str, val) -> None:
    if name in bsdf.inputs:
        bsdf.inputs[name].default_value = val


def get_rgba_mix_sockets(mix_node):
    rgba_in = [s for s in mix_node.inputs if s.type == "RGBA"]
    rgba_out = [s for s in mix_node.outputs if s.type == "RGBA"]
    return mix_node.inputs[0], rgba_in[0], rgba_in[1], rgba_out[0]


def _link_obj(scene, obj) -> None:
    if obj.name not in scene.collection.objects:
        scene.collection.objects.link(obj)


def _finalize_bmesh(
    scene,
    name: str,
    bm: bmesh.types.BMesh,
    mats=None,
    loc=(0.0, 0.0, 0.0),
    rot=(0.0, 0.0, 0.0),
    smooth: bool = True,
    edge_split_deg: float | None = None,
):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()

    obj = bpy.data.objects.new(name, mesh)
    obj.location = Vector(loc)
    obj.rotation_euler = Euler(rot, "XYZ")
    _link_obj(scene, obj)

    if smooth:
        for poly in mesh.polygons:
            poly.use_smooth = True
    if edge_split_deg is not None:
        es = obj.modifiers.new("SmoothSplit", "EDGE_SPLIT")
        es.split_angle = math.radians(edge_split_deg)
    if mats is not None:
        for m in (mats if isinstance(mats, (list, tuple)) else [mats]):
            obj.data.materials.append(m)
    return obj


# ============================================================================
# 2. PROCEDURAL PBR MATERIALS (1752 STORMY PHILADELPHIA PALETTE)
# ============================================================================
def _make_wet_cobblestone_mat(name: str = "ColonialWetCobblestone"):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]

    tc = nt.nodes.new("ShaderNodeTexCoord")
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.offset = 0.5
    br.inputs["Scale"].default_value = 3.2
    br.inputs["Mortar Size"].default_value = 0.025
    br.inputs["Mortar Smooth"].default_value = 0.35
    br.inputs["Color1"].default_value = (0.068, 0.072, 0.082, 1.0)
    br.inputs["Color2"].default_value = (0.095, 0.092, 0.088, 1.0)
    br.inputs["Mortar"].default_value = (0.018, 0.018, 0.020, 1.0)

    ns_puddle = nt.nodes.new("ShaderNodeTexNoise")
    ns_puddle.inputs["Scale"].default_value = 0.95
    ns_puddle.inputs["Detail"].default_value = 6.0
    ns_puddle.inputs["Roughness"].default_value = 0.55

    rmp_r = nt.nodes.new("ShaderNodeMapRange")
    rmp_r.clamp = True
    rmp_r.inputs["From Min"].default_value = 0.36
    rmp_r.inputs["From Max"].default_value = 0.68
    rmp_r.inputs["To Min"].default_value = 0.14  # Rain-glazed glossy storm puddles!
    rmp_r.inputs["To Max"].default_value = 0.72

    ao = nt.nodes.new("ShaderNodeAmbientOcclusion")
    ao.samples = 2
    ao.inputs["Distance"].default_value = 0.35
    mix_ao = nt.nodes.new("ShaderNodeMix")
    mix_ao.data_type = "RGBA"
    mix_ao.blend_type = "MULTIPLY"
    fac, a_in, b_in, out_c = get_rgba_mix_sockets(mix_ao)
    fac.default_value = 0.80

    bmp = nt.nodes.new("ShaderNodeBump")
    bmp.inputs["Strength"].default_value = 0.38
    bmp.inputs["Distance"].default_value = 0.018
    bmp.invert = True

    set_bsdf(bsdf, "Coat Weight", 0.45)
    set_bsdf(bsdf, "Coat Roughness", 0.12)

    nt.links.new(tc.outputs["Object"], br.inputs["Vector"])
    nt.links.new(tc.outputs["Object"], ns_puddle.inputs["Vector"])
    nt.links.new(br.outputs["Color"], a_in)
    nt.links.new(ao.outputs["Color"], b_in)
    nt.links.new(out_c, bsdf.inputs["Base Color"])
    nt.links.new(ns_puddle.outputs["Fac"], rmp_r.inputs["Value"])
    nt.links.new(rmp_r.outputs["Result"], bsdf.inputs["Roughness"])
    nt.links.new(br.outputs["Fac"], bmp.inputs["Height"])
    nt.links.new(bmp.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def _make_wet_meadow_mat(name: str = "StormWetMeadowGrass"):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    ns = nt.nodes.new("ShaderNodeTexNoise")
    ns.inputs["Scale"].default_value = 2.4
    ns.inputs["Detail"].default_value = 8.0
    ns.inputs["Roughness"].default_value = 0.65
    rmp = nt.nodes.new("ShaderNodeValToRGB")
    rmp.color_ramp.elements[0].position = 0.25
    rmp.color_ramp.elements[0].color = (0.018, 0.044, 0.024, 1.0)
    rmp.color_ramp.elements[-1].position = 0.78
    rmp.color_ramp.elements[-1].color = (0.042, 0.088, 0.036, 1.0)
    bmp = nt.nodes.new("ShaderNodeBump")
    bmp.inputs["Strength"].default_value = 0.22
    bmp.inputs["Distance"].default_value = 0.02
    set_bsdf(bsdf, "Roughness", 0.52)
    set_bsdf(bsdf, "Coat Weight", 0.22)
    set_bsdf(bsdf, "Coat Roughness", 0.25)
    nt.links.new(tc.outputs["Object"], ns.inputs["Vector"])
    nt.links.new(ns.outputs["Fac"], rmp.inputs["Fac"])
    nt.links.new(rmp.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(ns.outputs["Fac"], bmp.inputs["Height"])
    nt.links.new(bmp.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def _make_colonial_stone_mat(name: str = "ColonialSandstone", dark: bool = False):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    ns = nt.nodes.new("ShaderNodeTexNoise")
    ns.inputs["Scale"].default_value = 6.5
    ns.inputs["Detail"].default_value = 9.0
    rmp = nt.nodes.new("ShaderNodeValToRGB")
    if dark:
        rmp.color_ramp.elements[0].color = (0.028, 0.030, 0.038, 1.0)
        rmp.color_ramp.elements[-1].color = (0.068, 0.072, 0.084, 1.0)
    else:
        rmp.color_ramp.elements[0].color = (0.145, 0.128, 0.108, 1.0)
        rmp.color_ramp.elements[-1].color = (0.245, 0.215, 0.178, 1.0)
    bmp = nt.nodes.new("ShaderNodeBump")
    bmp.inputs["Strength"].default_value = 0.24
    bmp.inputs["Distance"].default_value = 0.012
    set_bsdf(bsdf, "Roughness", 0.56)
    nt.links.new(tc.outputs["Object"], ns.inputs["Vector"])
    nt.links.new(ns.outputs["Fac"], rmp.inputs["Fac"])
    nt.links.new(rmp.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(ns.outputs["Fac"], bmp.inputs["Height"])
    nt.links.new(bmp.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def _make_dark_timber_mat(name: str = "ColonialWeatheredOak"):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.5, 1.5, 9.0)
    ns = nt.nodes.new("ShaderNodeTexNoise")
    ns.inputs["Scale"].default_value = 5.0
    ns.inputs["Detail"].default_value = 8.0
    rmp = nt.nodes.new("ShaderNodeValToRGB")
    rmp.color_ramp.elements[0].color = (0.048, 0.026, 0.014, 1.0)
    rmp.color_ramp.elements[-1].color = (0.115, 0.066, 0.034, 1.0)
    bmp = nt.nodes.new("ShaderNodeBump")
    bmp.inputs["Strength"].default_value = 0.20
    bmp.inputs["Distance"].default_value = 0.008
    set_bsdf(bsdf, "Roughness", 0.58)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], ns.inputs["Vector"])
    nt.links.new(ns.outputs["Fac"], rmp.inputs["Fac"])
    nt.links.new(rmp.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(ns.outputs["Fac"], bmp.inputs["Height"])
    nt.links.new(bmp.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def _make_brass_accent_mat(name: str = "ColonialBrassTrim"):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    set_bsdf(bsdf, "Base Color", (0.78, 0.56, 0.22, 1.0))
    set_bsdf(bsdf, "Metallic", 0.96)
    set_bsdf(bsdf, "Roughness", 0.24)
    return mat


def _make_brick_manor_mat(name: str = "PhiladelphiaColonialBrick"):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.inputs["Scale"].default_value = 6.0
    br.inputs["Color1"].default_value = (0.16, 0.048, 0.034, 1.0)
    br.inputs["Color2"].default_value = (0.22, 0.068, 0.044, 1.0)
    br.inputs["Mortar"].default_value = (0.11, 0.10, 0.09, 1.0)
    set_bsdf(bsdf, "Roughness", 0.72)
    nt.links.new(tc.outputs["Object"], br.inputs["Vector"])
    nt.links.new(br.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


# ============================================================================
# 3. ANIMATED STORMY SKY -> STARRY ELECTRIC-AGE COSMOS
# ============================================================================
def _setup_storm_to_cosmos_world(scene):
    world = bpy.data.worlds.new("FranklinStormWorld")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputWorld")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")

    # Storm horizon-to-zenith gradient (dramatic teal-cobalt storm twilight with thundercloud bands)
    ns_cloud = nt.nodes.new("ShaderNodeTexNoise")
    ns_cloud.inputs["Scale"].default_value = 3.2
    ns_cloud.inputs["Detail"].default_value = 8.0
    ns_cloud.inputs["Roughness"].default_value = 0.62

    rmp_storm = nt.nodes.new("ShaderNodeValToRGB")
    rmp_storm.color_ramp.elements[0].position = 0.0
    rmp_storm.color_ramp.elements[0].color = (0.045, 0.085, 0.145, 1.0)  # Moody storm horizon
    e_m = rmp_storm.color_ramp.elements.new(0.32)
    e_m.color = (0.018, 0.036, 0.082, 1.0)  # Deep storm cloud cobalt
    rmp_storm.color_ramp.elements[-1].position = 0.85
    rmp_storm.color_ramp.elements[-1].color = (0.008, 0.014, 0.038, 1.0)  # Thunderhead zenith

    # Modulate storm sky with electric-blue cloud wisps
    rmp_cloud = nt.nodes.new("ShaderNodeValToRGB")
    rmp_cloud.color_ramp.elements[0].position = 0.42
    rmp_cloud.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    rmp_cloud.color_ramp.elements[-1].position = 0.78
    rmp_cloud.color_ramp.elements[-1].color = (0.08, 0.16, 0.28, 1.0)

    mix_storm = nt.nodes.new("ShaderNodeMix")
    mix_storm.data_type = "RGBA"
    mix_storm.blend_type = "ADD"
    ms_f, ms_a, ms_b, ms_out = get_rgba_mix_sockets(mix_storm)
    ms_f.default_value = 0.85

    # Starry twilight sky (Beats 5-6)
    rmp_night = nt.nodes.new("ShaderNodeValToRGB")
    rmp_night.color_ramp.elements[0].position = 0.0
    rmp_night.color_ramp.elements[0].color = (0.012, 0.024, 0.056, 1.0)
    rmp_night.color_ramp.elements[-1].position = 0.75
    rmp_night.color_ramp.elements[-1].color = (0.003, 0.006, 0.020, 1.0)

    mix_sky = nt.nodes.new("ShaderNodeMix")
    mix_sky.data_type = "RGBA"
    sky_fac, sky_a, sky_b, sky_out = get_rgba_mix_sockets(mix_sky)
    sky_fac.default_value = 0.0

    # Lightning flash strobe boost into sky
    mix_flash = nt.nodes.new("ShaderNodeMix")
    mix_flash.data_type = "RGBA"
    mix_flash.blend_type = "ADD"
    fl_fac, fl_a, fl_b, fl_out = get_rgba_mix_sockets(mix_flash)
    fl_fac.default_value = 0.0
    fl_b.default_value = (0.35, 0.68, 1.0, 1.0)

    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = 0.95

    nt.links.new(tc.outputs["Generated"], sep.inputs["Vector"])
    nt.links.new(tc.outputs["Generated"], ns_cloud.inputs["Vector"])
    nt.links.new(sep.outputs["Z"], rmp_storm.inputs["Fac"])
    nt.links.new(sep.outputs["Z"], rmp_night.inputs["Fac"])
    nt.links.new(ns_cloud.outputs["Fac"], rmp_cloud.inputs["Fac"])
    nt.links.new(rmp_storm.outputs["Color"], ms_a)
    nt.links.new(rmp_cloud.outputs["Color"], ms_b)
    nt.links.new(ms_out, sky_a)
    nt.links.new(rmp_night.outputs["Color"], sky_b)
    nt.links.new(sky_out, fl_a)
    nt.links.new(fl_out, bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])

    return sky_fac, fl_fac, bg.inputs["Strength"]


# ============================================================================
# 4. GEOMETRY BUILDERS (COURTYARD, PLINTHS, COLONIAL MANOR, FENCE, LANTERN, STARS)
# ============================================================================
def _build_plinth(scene, name: str, top_pos: Vector, stone_mat, oak_mat, brass_mat, width: float = 0.56):
    bm = bmesh.new()
    h = top_pos.z
    # Base molding
    bmesh.ops.create_cube(
        bm, size=1.0,
        matrix=Matrix.Translation((0, 0, 0.06)) @ Matrix.Diagonal((width * 1.18, width * 1.18, 0.12, 1.0)),
    )
    # Main stone shaft
    bmesh.ops.create_cube(
        bm, size=1.0,
        matrix=Matrix.Translation((0, 0, h * 0.50)) @ Matrix.Diagonal((width * 0.92, width * 0.92, h - 0.16, 1.0)),
    )
    _finalize_bmesh(scene, f"{name}_Stone", bm, stone_mat, loc=(top_pos.x, top_pos.y, 0.0), smooth=False)

    # Dark oak tabletop slab
    bm_top = bmesh.new()
    bmesh.ops.create_cube(
        bm_top, size=1.0,
        matrix=Matrix.Translation((0, 0, h - 0.035)) @ Matrix.Diagonal((width * 1.12, width * 1.12, 0.07, 1.0)),
    )
    _finalize_bmesh(scene, f"{name}_Top", bm_top, oak_mat, loc=(top_pos.x, top_pos.y, 0.0), smooth=False)

    # Antique brass corner trim ring
    bm_br = bmesh.new()
    bmesh.ops.create_cone(
        bm_br, cap_ends=True, cap_tris=False, segments=24,
        radius1=width * 0.44, radius2=width * 0.44, depth=0.012,
        matrix=Matrix.Translation((0, 0, h - 0.002)),
    )
    _finalize_bmesh(scene, f"{name}_BrassInlay", bm_br, brass_mat, loc=(top_pos.x, top_pos.y, 0.0), smooth=True)


def _build_colonial_background(scene, brick_mat, oak_mat, stone_mat, brass_mat):
    # Rain-glazed cobblestone terrace (X in [-6, +6], Y in [-4, +4])
    bm_c = bmesh.new()
    bmesh.ops.create_grid(
        bm_c, x_segments=12, y_segments=10, size=6.0,
        matrix=Matrix.Translation((0.0, 0.0, 0.0)),
    )
    _finalize_bmesh(scene, "ColonialCobblestoneTerrace", bm_c, _make_wet_cobblestone_mat(), smooth=False)

    # Outer rolling wet meadow grass surround
    bm_m = bmesh.new()
    bmesh.ops.create_grid(
        bm_m, x_segments=28, y_segments=24, size=26.0,
        matrix=Matrix.Translation((0.0, 12.0, -0.02)),
    )
    for v in bm_m.verts:
        if v.co.y > 4.2:
            ridge = 0.55 * math.sin(v.co.x * 0.24) + 0.35 * math.cos(v.co.y * 0.18)
            v.co.z += max(0.0, (v.co.y - 4.2) * 0.085 + ridge * 0.28)
    _finalize_bmesh(scene, "PhiladelphiaStormMeadow", bm_m, _make_wet_meadow_mat(), smooth=True)

    # Colonial split-rail wooden meadow fence along Y = +3.35m (frames characters cleanly without blocking sky)
    bm_f = bmesh.new()
    for px in [-5.4, -3.6, -1.8, 0.0, 1.8, 3.6, 5.4]:
        bmesh.ops.create_cube(
            bm_f, size=1.0,
            matrix=Matrix.Translation((px, 3.35, 0.46)) @ Matrix.Diagonal((0.11, 0.11, 0.94, 1.0)),
        )
    for rz in (0.34, 0.68):
        bmesh.ops.create_cube(
            bm_f, size=1.0,
            matrix=Matrix.Translation((0.0, 3.35, rz)) @ Matrix.Diagonal((11.2, 0.055, 0.075, 1.0)),
        )
    _finalize_bmesh(scene, "ColonialSplitRailFence", bm_f, oak_mat, smooth=False)

    # Beat 3 shaded colonial stone alcove backdrop (X in [-3.85, -1.70], Y = +1.35) so Leyden Jar plasma pops!
    bm_alc = bmesh.new()
    bmesh.ops.create_cube(
        bm_alc, size=1.0,
        matrix=Matrix.Translation((-2.78, 1.48, 1.45)) @ Matrix.Diagonal((2.20, 0.24, 2.95, 1.0)),
    )
    _finalize_bmesh(scene, "ColonialAlcoveWall", bm_alc, _make_colonial_stone_mat("DarkAlcoveStone", dark=True), smooth=False)

    # Distant 1752 Philadelphia brick colonial manor silhouette (Y = +10.5m, left-rear so Beat 6 center sky stays open)
    bm_h = bmesh.new()
    bmesh.ops.create_cube(
        bm_h, size=1.0,
        matrix=Matrix.Translation((-4.4, 10.8, 1.85)) @ Matrix.Diagonal((4.2, 2.8, 3.7, 1.0)),
    )
    _finalize_bmesh(scene, "ColonialManorBody", bm_h, brick_mat, smooth=False)

    # Warm candlelit manor windows (rich warm-amber counterpoint to electric blue!)
    win_mat = bpy.data.materials.new("ManorWarmWindow")
    win_mat.use_nodes = True
    nt = win_mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (1.0, 0.68, 0.26, 1.0)
    em.inputs["Strength"].default_value = 3.4
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])

    bm_w = bmesh.new()
    for wx in (-5.4, -4.4, -3.4):
        for wz in (1.35, 2.55):
            bmesh.ops.create_cube(
                bm_w, size=1.0,
                matrix=Matrix.Translation((wx, 9.36, wz)) @ Matrix.Diagonal((0.46, 0.06, 0.66, 1.0)),
            )
    _finalize_bmesh(scene, "ColonialManorWindows", bm_w, win_mat, smooth=False)

    # Flickering colonial brass pier lantern at (+1.88, +1.55, 1.25)
    bm_post = bmesh.new()
    bmesh.ops.create_cube(
        bm_post, size=1.0,
        matrix=Matrix.Translation((1.88, 1.55, 0.62)) @ Matrix.Diagonal((0.24, 0.24, 1.24, 1.0)),
    )
    _finalize_bmesh(scene, "LanternPier", bm_post, stone_mat, smooth=False)

    lan_mat = bpy.data.materials.new("ColonialLanternGlow")
    lan_mat.use_nodes = True
    nt = lan_mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em_l = nt.nodes.new("ShaderNodeEmission")
    em_l.inputs["Color"].default_value = (1.0, 0.72, 0.30, 1.0)
    em_l.inputs["Strength"].default_value = 5.5
    nt.links.new(em_l.outputs["Emission"], out.inputs["Surface"])

    bm_l = bmesh.new()
    bmesh.ops.create_cone(
        bm_l, cap_ends=True, cap_tris=False, segments=6,
        radius1=0.075, radius2=0.095, depth=0.22,
        matrix=Matrix.Translation((1.88, 1.55, 1.38)),
    )
    _finalize_bmesh(scene, "ColonialLanternGlass", bm_l, lan_mat, smooth=False)

    bm_cap = bmesh.new()
    bmesh.ops.create_cone(
        bm_cap, cap_ends=True, cap_tris=False, segments=6,
        radius1=0.125, radius2=0.02, depth=0.11,
        matrix=Matrix.Translation((1.88, 1.55, 1.54)),
    )
    _finalize_bmesh(scene, "ColonialLanternCap", bm_cap, brass_mat, smooth=False)

    lan_light_data = bpy.data.lights.new("ColonialLanternLight", type="POINT")
    lan_light_data.energy = 32.0
    lan_light_data.color = (1.0, 0.68, 0.28)
    lan_light_data.shadow_soft_size = 0.22
    lan_light = bpy.data.objects.new("ColonialLanternLight", lan_light_data)
    lan_light.location = Vector((1.88, 1.48, 1.38))
    _link_obj(scene, lan_light)

    return em_l.inputs["Strength"], lan_light


def _build_stars_and_moon(scene):
    rng = random.Random(1752)
    star_mat = bpy.data.materials.new("StarlightMat")
    star_mat.use_nodes = True
    nt = star_mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (0.86, 0.94, 1.0, 1.0)
    em.inputs["Strength"].default_value = 0.0
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])

    bm = bmesh.new()
    for _ in range(160):
        az = rng.uniform(-1.35, 1.35)
        el = rng.uniform(0.18, 0.78)
        dist = rng.uniform(22.0, 28.0)
        sx = dist * math.sin(az)
        sy = dist * math.cos(az) * math.cos(el)
        sz = 1.6 + dist * math.sin(el)
        r = rng.uniform(0.032, 0.075)
        bmesh.ops.create_icosphere(bm, subdivisions=1, radius=r, matrix=Matrix.Translation((sx, sy, sz)))
    stars_obj = _finalize_bmesh(scene, "StarField3D", bm, star_mat, smooth=True)
    stars_obj.visible_shadow = False

    # Sculpted Crescent Moon placed cleanly right/high (clear of Beat 6 center sky monument!)
    moon_mat = bpy.data.materials.new("CrescentMoonMat")
    moon_mat.use_nodes = True
    nt = moon_mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em_m = nt.nodes.new("ShaderNodeEmission")
    em_m.inputs["Color"].default_value = (0.96, 0.94, 0.86, 1.0)
    em_m.inputs["Strength"].default_value = 0.0
    nt.links.new(em_m.outputs["Emission"], out.inputs["Surface"])

    bm_m = bmesh.new()
    segs = 28
    verts_outer = []
    verts_inner = []
    for i in range(segs + 1):
        ang = -math.pi * 0.58 + (math.pi * 1.16) * (i / segs)
        xo = 0.78 * math.cos(ang)
        zo = 0.78 * math.sin(ang)
        xi = 0.24 + 0.62 * math.cos(ang)
        zi = 0.68 * math.sin(ang)
        verts_outer.append(bm_m.verts.new((xo, 0.0, zo)))
        verts_inner.append(bm_m.verts.new((xi, 0.0, zi)))
    for i in range(segs):
        bm_m.faces.new((verts_outer[i], verts_outer[i + 1], verts_inner[i + 1], verts_inner[i]))
    moon_obj = _finalize_bmesh(scene, "CrescentMoon3D", bm_m, moon_mat, loc=CRESCENT_MOON_POS, smooth=True)
    moon_obj.visible_shadow = False
    return em.inputs["Strength"], em_m.inputs["Strength"]


def _build_storm_lighting_rig(scene):
    # 1. Warm Colonial Key Light (Rembrandt warm amber balancing cool electric storm!)
    key_data = bpy.data.lights.new("FranklinKeyLight", type="AREA")
    key_data.shape = "RECTANGLE"
    key_data.size = 2.4
    key_data.size_y = 2.0
    key_data.energy = 240.0
    key_data.color = (1.0, 0.80, 0.56)
    key_obj = bpy.data.objects.new("FranklinKeyLight", key_data)
    key_obj.location = Vector((-2.4, -2.6, 3.0))
    _link_obj(scene, key_obj)

    # 2. Electric-Blue Storm Rim Light (crisp dramatic cyan-cobalt edge separation on coats & hair!)
    rim_data = bpy.data.lights.new("FranklinStormRimLight", type="AREA")
    rim_data.shape = "RECTANGLE"
    rim_data.size = 3.2
    rim_data.size_y = 2.0
    rim_data.energy = 320.0
    rim_data.color = (0.34, 0.72, 1.0)
    rim_obj = bpy.data.objects.new("FranklinStormRimLight", rim_data)
    rim_obj.location = Vector((2.6, 2.8, 3.2))
    _link_obj(scene, rim_obj)

    # 3. Dynamic Lightning Flash Strobe SUN (pulses dramatically on lightning impacts!)
    flash_data = bpy.data.lights.new("LightningFlashSun", type="SUN")
    flash_data.energy = 0.85
    flash_data.color = (0.62, 0.86, 1.0)
    flash_data.angle = math.radians(14.0)
    flash_obj = bpy.data.objects.new("LightningFlashSun", flash_data)
    flash_obj.rotation_euler = Euler((math.radians(52.0), math.radians(-18.0), math.radians(24.0)), "XYZ")
    _link_obj(scene, flash_obj)

    # 4. Meadow Bounce Fill (keeps faces & dark velvet coats sculpted, never black mud)
    fill_data = bpy.data.lights.new("FranklinMeadowBounce", type="AREA")
    fill_data.shape = "RECTANGLE"
    fill_data.size = 3.0
    fill_data.size_y = 1.6
    fill_data.energy = 62.0
    fill_data.color = (0.72, 0.82, 0.96)
    fill_obj = bpy.data.objects.new("FranklinMeadowBounce", fill_data)
    fill_obj.location = Vector((0.0, -2.2, 1.48))
    _link_obj(scene, fill_obj)

    # 5. AGENTS.md Section 1 Mandatory 0.42m Softbox Eye Catchlight (AREA, NEVER tiny POINT!)
    catch_data = bpy.data.lights.new("FranklinEyeCatchlight", type="AREA")
    catch_data.shape = "DISK"
    catch_data.size = 0.42
    catch_data.energy = 56.0
    catch_data.color = (0.96, 0.98, 1.0)
    if hasattr(catch_data, "diffuse_factor"):
        catch_data.diffuse_factor = 0.28
    if hasattr(catch_data, "specular_factor"):
        catch_data.specular_factor = 1.75
    catch_obj = bpy.data.objects.new("FranklinEyeCatchlight", catch_data)
    catch_obj.location = Vector((0.0, -1.8, 1.85))
    _link_obj(scene, catch_obj)

    return {
        "key_light": key_obj,
        "rim_light": rim_obj,
        "flash_sun": flash_obj,
        "fill_light": fill_obj,
        "catch_light": catch_obj,
    }


def build_franklin_world(scene) -> dict:
    sky_fac, flash_fac, bg_str = _setup_storm_to_cosmos_world(scene)
    stone_mat = _make_colonial_stone_mat()
    oak_mat = _make_dark_timber_mat()
    brass_mat = _make_brass_accent_mat()
    brick_mat = _make_brick_manor_mat()

    lantern_em, lantern_light = _build_colonial_background(scene, brick_mat, oak_mat, stone_mat, brass_mat)
    _build_plinth(scene, "KiteKeyPlinth", KITE_KEY_PLINTH, stone_mat, oak_mat, brass_mat, width=0.52)
    _build_plinth(scene, "KeyStandPlinth", KEY_STAND_PLINTH, stone_mat, oak_mat, brass_mat, width=0.54)
    _build_plinth(scene, "SteeplePlinth", STEEPLE_PLINTH, stone_mat, oak_mat, brass_mat, width=0.60)

    star_str, moon_str = _build_stars_and_moon(scene)
    lights = _build_storm_lighting_rig(scene)

    # Atmospheric electric-blue storm spark motes / twilight fireflies
    mote_mat = bpy.data.materials.new("StormElectricMoteMat")
    mote_mat.use_nodes = True
    nt = mote_mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em_p = nt.nodes.new("ShaderNodeEmission")
    em_p.inputs["Color"].default_value = (0.45, 0.88, 1.0, 1.0)
    em_p.inputs["Strength"].default_value = 2.6
    nt.links.new(em_p.outputs["Emission"], out.inputs["Surface"])

    rng = random.Random(17520)
    motes = []
    for i in range(28):
        bm_p = bmesh.new()
        bmesh.ops.create_icosphere(bm_p, subdivisions=1, radius=0.0085)
        bp = Vector((rng.uniform(-3.4, 3.4), rng.uniform(-0.4, 2.2), rng.uniform(0.35, 2.25)))
        obj = _finalize_bmesh(scene, f"ElectricMote_{i:02d}", bm_p, mote_mat, loc=bp, smooth=True)
        obj.visible_shadow = False
        motes.append((obj, bp, rng.uniform(0.8, 2.2), rng.uniform(0.0, 6.28)))

    return {
        "sky_fac": sky_fac,
        "flash_fac": flash_fac,
        "bg_strength": bg_str,
        "star_strength": star_str,
        "moon_strength": moon_str,
        "lantern_em": lantern_em,
        "lantern_light": lantern_light,
        "motes": motes,
        "mote_color": em_p.inputs["Color"],
        **lights,
    }


def _lightning_pulse(t: float, t_hit: float, width: float = 0.24) -> float:
    dt = t - t_hit
    if dt < -0.05 or dt > width * 2.5:
        return 0.0
    main_p = math.exp(-((dt / max(0.03, width * 0.42)) ** 2))
    re_strike = 0.65 * math.exp(-(((dt - 0.14) / max(0.03, width * 0.28)) ** 2))
    return clamp01(main_p + re_strike)


def animate_franklin_world(world_handles: dict, frame: int, t: float, focus_x: float = 0.0) -> None:
    night_fac = smoothstep(20.0, 22.0, t)
    # Synchronized storm lightning strobe pulses on Beat 1 (2.08s), Beat 2 spark (7.02s), Beat 4 rod strike (17.42s)
    flash = clamp01(
        _lightning_pulse(t, 2.08, 0.30)
        + 0.45 * _lightning_pulse(t, 7.02, 0.18)
        + _lightning_pulse(t, 17.42, 0.32)
        + 0.30 * _lightning_pulse(t, 26.80, 0.22)
    )

    world_handles["sky_fac"].default_value = night_fac
    world_handles["sky_fac"].keyframe_insert(data_path="default_value", frame=frame)

    world_handles["flash_fac"].default_value = flash * 0.85
    world_handles["flash_fac"].keyframe_insert(data_path="default_value", frame=frame)

    world_handles["bg_strength"].default_value = lerp(0.92, 0.72, night_fac) + flash * 0.95
    world_handles["bg_strength"].keyframe_insert(data_path="default_value", frame=frame)

    world_handles["star_strength"].default_value = lerp(0.0, 2.8, night_fac)
    world_handles["star_strength"].keyframe_insert(data_path="default_value", frame=frame)
    world_handles["moon_strength"].default_value = lerp(0.0, 2.1, night_fac)
    world_handles["moon_strength"].keyframe_insert(data_path="default_value", frame=frame)

    # Flickering colonial lantern
    flk = 1.0 + 0.09 * math.sin(t * 13.4) + 0.05 * math.cos(t * 21.7)
    world_handles["lantern_em"].default_value = lerp(4.8, 6.8, night_fac) * flk
    world_handles["lantern_em"].keyframe_insert(data_path="default_value", frame=frame)
    world_handles["lantern_light"].data.energy = lerp(28.0, 42.0, night_fac) * flk
    world_handles["lantern_light"].data.keyframe_insert(data_path="energy", frame=frame)

    # Track key/rim/fill/catchlight smoothly onto active Beat station X
    aim_pt = Vector((focus_x, 0.22, 1.48))
    eye_pt = Vector((focus_x, 0.32, 1.62))

    key_obj = world_handles["key_light"]
    key_obj.location = Vector((focus_x - 2.1, -2.4, 2.9))
    key_obj.rotation_euler = (aim_pt - key_obj.location).to_track_quat("-Z", "Y").to_euler()
    key_obj.keyframe_insert(data_path="location", frame=frame)
    key_obj.keyframe_insert(data_path="rotation_euler", frame=frame)
    key_obj.data.energy = lerp(245.0, 175.0, night_fac)
    key_obj.data.keyframe_insert(data_path="energy", frame=frame)

    rim_obj = world_handles["rim_light"]
    rim_obj.location = Vector((focus_x + 2.2, 2.5, 3.0))
    rim_obj.rotation_euler = (aim_pt - rim_obj.location).to_track_quat("-Z", "Y").to_euler()
    rim_obj.keyframe_insert(data_path="location", frame=frame)
    rim_obj.keyframe_insert(data_path="rotation_euler", frame=frame)
    rim_obj.data.energy = lerp(310.0, 380.0, night_fac) + flash * 420.0
    rim_obj.data.keyframe_insert(data_path="energy", frame=frame)

    flash_sun = world_handles["flash_sun"]
    flash_sun.data.energy = lerp(0.95, 0.65, night_fac) + flash * 5.2
    flash_sun.data.keyframe_insert(data_path="energy", frame=frame)

    fill_obj = world_handles["fill_light"]
    fill_obj.location = Vector((focus_x, -2.2, 1.48))
    fill_obj.rotation_euler = (aim_pt - fill_obj.location).to_track_quat("-Z", "Y").to_euler()
    fill_obj.keyframe_insert(data_path="location", frame=frame)
    fill_obj.keyframe_insert(data_path="rotation_euler", frame=frame)

    catch_obj = world_handles["catch_light"]
    catch_obj.location = Vector((focus_x + 0.16, -1.65, 1.82))
    catch_obj.rotation_euler = (eye_pt - catch_obj.location).to_track_quat("-Z", "Y").to_euler()
    catch_obj.keyframe_insert(data_path="location", frame=frame)
    catch_obj.keyframe_insert(data_path="rotation_euler", frame=frame)
    catch_obj.data.energy = lerp(54.0, 64.0, night_fac)
    catch_obj.data.keyframe_insert(data_path="energy", frame=frame)

    # Drifting storm sparks -> warm golden electric fireflies
    mc = world_handles["mote_color"]
    mc.default_value = (lerp(0.42, 1.00, night_fac), lerp(0.86, 0.84, night_fac), lerp(1.00, 0.36, night_fac), 1.0)
    mc.keyframe_insert(data_path="default_value", frame=frame)
    for obj, bp, spd, ph in world_handles["motes"]:
        obj.location = Vector((
            bp.x + 0.12 * math.sin(t * spd + ph),
            bp.y + 0.08 * math.cos(t * spd * 0.8 + ph),
            bp.z + 0.09 * math.sin(t * spd * 1.1 + ph),
        ))
        obj.keyframe_insert(data_path="location", frame=frame)
