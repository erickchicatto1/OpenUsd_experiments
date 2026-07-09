import sys
import os
import random
from pathlib import Path
from typing import Tuple

from pxr import Usd, UsdShade, UsdGeom, Sdf

sys.path.insert(0, str(Path(__file__).parent))

from usd_scene_construction_utils import (
    add_usd_ref,
    rotate_x,
    rotate_y,
    rotate_z,
    scale,
    compute_bbox,
    add_xform,
    compute_bbox_center,
    translate,
    set_visibility,
    new_in_memory_stage,
    add_dome_light,
    add_plane,
    add_preview_material,
    bind_material,
    export_stage,
)


# ===========================================================================
# SECCION 1: Conversion de materiales MDL (OmniPBR/OmniSurface) a
# UsdPreviewSurface, para que se vean bien en usdview/Blender.
# ===========================================================================

# Nombres de inputs mas comunes en shaders MDL de NVIDIA (OmniPBR / OmniSurface).
# Se intenta cada alias en orden hasta encontrar uno presente.
_COLOR_ALIASES = ["diffuse_color_constant", "diffuseColor", "albedo_color", "base_color_constant"]
_ROUGHNESS_ALIASES = ["reflection_roughness_constant", "roughness_constant", "roughness"]
_METALLIC_ALIASES = ["metallic_constant", "metalness_constant", "metallic"]
_OPACITY_ALIASES = ["opacity_constant", "opacity"]
_DIFFUSE_TEX_ALIASES = ["diffuse_texture", "albedo_texture", "base_color_texture"]
_NORMAL_TEX_ALIASES = ["normalmap_texture", "normal_texture"]
_ORM_TEX_ALIASES = ["ORM_texture", "orm_texture"]


def _find_shader_input(shader: UsdShade.Shader, aliases):
    """Devuelve el primer UsdShade.Input existente en 'shader' cuyo nombre
    coincida con alguno de los alias dados, o None si no hay ninguno."""
    for name in aliases:
        inp = shader.GetInput(name)
        if inp and inp.Get() is not None:
            return inp
    return None


def _is_mdl_shader(shader: UsdShade.Shader) -> bool:
    """True si el shader usa un sourceAsset MDL (ej. OmniPBR.mdl)."""
    impl_src = shader.GetImplementationSourceAttr()
    if impl_src and impl_src.Get() == UsdShade.Tokens.sourceAsset:
        asset_attr = shader.GetSourceAsset("mdl")
        if asset_attr:
            return True
    id_attr = shader.GetIdAttr()
    if id_attr and id_attr.Get():
        val = str(id_attr.Get()).lower()
        if "mdl" in val or "omnipbr" in val or "omnisurface" in val:
            return True
    return False


def find_mdl_materials(stage: Usd.Stage, root_prim: Usd.Prim):
    """Recorre root_prim y devuelve una lista de (material_prim, shader_prim)
    para cada material que use un shader MDL."""
    results = []
    for prim in Usd.PrimRange(root_prim):
        if not prim.IsA(UsdShade.Material):
            continue
        for child in prim.GetChildren():
            if child.IsA(UsdShade.Shader):
                shader = UsdShade.Shader(child)
                if _is_mdl_shader(shader):
                    results.append((prim, child))
    return results


def inspect_materials(stage: Usd.Stage, root_prim: Usd.Prim):
    """Imprime en consola que materiales/shaders MDL se encontraron y que
    inputs tienen. Util como primer paso de diagnostico con tus assets reales."""
    found = find_mdl_materials(stage, root_prim)
    if not found:
        print(f"No se encontraron shaders MDL bajo {root_prim.GetPath()}")
        return found

    for mat_prim, shader_prim in found:
        shader = UsdShade.Shader(shader_prim)
        print(f"\nMaterial: {mat_prim.GetPath()}")
        print(f"  Shader:  {shader_prim.GetPath()}")
        for inp in shader.GetInputs():
            try:
                val = inp.Get()
            except Exception:
                val = "<no evaluable>"
            print(f"    input {inp.GetBaseName():30s} = {val}")
    return found


def _resolve_texture_path(tex_value, asset_dir):
    """Convierte el AssetPath guardado en el shader MDL en una ruta usable
    por UsdUVTexture. Si es relativa, la busca dentro de asset_dir."""
    if tex_value is None:
        return None
    raw = tex_value.path if isinstance(tex_value, Sdf.AssetPath) else str(tex_value)
    if not raw:
        return None
    if os.path.isabs(raw) and os.path.exists(raw):
        return raw
    if asset_dir:
        candidate = os.path.join(asset_dir, raw)
        if os.path.exists(candidate):
            return candidate
    return raw


def _make_preview_surface_material(stage, mat_path, color, roughness, metallic,
                                    opacity, diffuse_tex, asset_dir):
    """Crea un material UsdPreviewSurface en mat_path con los valores dados,
    con soporte opcional de textura difusa."""
    material = UsdShade.Material.Define(stage, mat_path)
    shader = UsdShade.Shader.Define(stage, f"{mat_path}/PreviewSurface")
    shader.CreateIdAttr("UsdPreviewSurface")

    diffuse_input = shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f)

    tex_path = _resolve_texture_path(diffuse_tex, asset_dir) if diffuse_tex else None
    if tex_path and os.path.exists(tex_path):
        st_reader = UsdShade.Shader.Define(stage, f"{mat_path}/stReader")
        st_reader.CreateIdAttr("UsdPrimvarReader_float2")
        st_reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
        st_output = st_reader.CreateOutput("result", Sdf.ValueTypeNames.Float2)

        tex_shader = UsdShade.Shader.Define(stage, f"{mat_path}/diffuseTexture")
        tex_shader.CreateIdAttr("UsdUVTexture")
        tex_shader.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(tex_path))
        tex_shader.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(st_output)
        tex_rgb_out = tex_shader.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)

        diffuse_input.ConnectToSource(tex_rgb_out)
        print(f"  -> textura difusa vinculada: {tex_path}")
    else:
        diffuse_input.Set(tuple(color) if color else (0.7, 0.7, 0.7))
        if diffuse_tex and not tex_path:
            print(f"  -> aviso: textura referenciada '{diffuse_tex}' no encontrada en disco, uso color plano")

    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(
        float(roughness) if roughness is not None else 0.5)
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(
        float(metallic) if metallic is not None else 0.0)
    shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(
        float(opacity) if opacity is not None else 1.0)

    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return material


def convert_mdl_materials_to_preview(stage: Usd.Stage, root_prim: Usd.Prim,
                                      asset_dir: str = None, verbose: bool = True):
    """
    Recorre root_prim, encuentra cada material con shader MDL, lee sus
    valores (color/roughness/metallic/opacity/texturas) y crea un material
    UsdPreviewSurface equivalente bajo <material_path>_preview, re-vinculando
    todas las geometrias que usaban el material original.
    """
    found = find_mdl_materials(stage, root_prim)
    if not found and verbose:
        print(f"[mdl_to_preview] No hay materiales MDL bajo {root_prim.GetPath()}; nada que convertir.")

    new_materials = []
    for mat_prim, shader_prim in found:
        shader = UsdShade.Shader(shader_prim)

        color_input = _find_shader_input(shader, _COLOR_ALIASES)
        rough_input = _find_shader_input(shader, _ROUGHNESS_ALIASES)
        metal_input = _find_shader_input(shader, _METALLIC_ALIASES)
        opacity_input = _find_shader_input(shader, _OPACITY_ALIASES)
        diffuse_tex_input = _find_shader_input(shader, _DIFFUSE_TEX_ALIASES)

        color = color_input.Get() if color_input else None
        roughness = rough_input.Get() if rough_input else None
        metallic = metal_input.Get() if metal_input else None
        opacity = opacity_input.Get() if opacity_input else None
        diffuse_tex = diffuse_tex_input.Get() if diffuse_tex_input else None

        preview_path = Sdf.Path(str(mat_prim.GetPath()) + "_preview")
        if verbose:
            print(f"[mdl_to_preview] Convirtiendo {mat_prim.GetPath()} -> {preview_path}")

        preview_mat = _make_preview_surface_material(
            stage, preview_path, color, roughness, metallic, opacity, diffuse_tex, asset_dir)
        new_materials.append(preview_mat)

        material_api = UsdShade.MaterialBindingAPI
        for prim in Usd.PrimRange(root_prim):
            if not (prim.IsA(UsdGeom.Gprim) or prim.IsA(UsdGeom.Mesh)):
                continue
            bound, rel = material_api(prim).ComputeBoundMaterial()
            if bound and bound.GetPrim().GetPath() == mat_prim.GetPath():
                material_api(prim).Bind(preview_mat)
                if verbose:
                    print(f"    rebind: {prim.GetPath()}")

    return new_materials


# ===========================================================================
# SECCION 2: Rutas de assets y configuracion
# ===========================================================================

ASSETS_DIR = os.environ.get("USD_ASSETS_DIR", r"D:\Robotics_AI\5.OpenUSD\assets")

box_asset_path = os.path.join(
    ASSETS_DIR,
    "Assets", "DigitalTwin", "Assets", "Warehouse", "Shipping",
    "Cardboard_Boxes", "Flat_A", "FlatBox_A02_15x21x8cm_PR_NVD_01.usd")

hand_truck_asset_path = os.path.join(
    ASSETS_DIR,
    "Assets", "DigitalTwin", "Assets", "Warehouse", "Equipment",
    "Hand_Trucks", "Convertible_Aluminum_A",
    "ConvertableAlumHandTruck_A02_PR_NVD_01.usd")

BOX_ASSET_DIR = os.path.dirname(box_asset_path)
HAND_TRUCK_ASSET_DIR = os.path.dirname(hand_truck_asset_path)

# Poner en True una sola vez para imprimir en consola los materiales MDL
# reales que traen tus assets. Util si algun color no sale como esperas.
DEBUG_INSPECT_MATERIALS = False

OUTPUT_USD = "escena_hand_trucks.usd"

for p in (box_asset_path, hand_truck_asset_path):
    if not os.path.exists(p):
        raise FileNotFoundError(
            f"No se encontro el asset: {p}\n"
            "Descargalo con descargar_assets.py o ajusta ASSETS_DIR.")


# ===========================================================================
# SECCION 3: Construccion de hand trucks + cajas
# ===========================================================================

def add_box_of_size(stage, path: str, size: Tuple[float, float, float]):
    """Adds a box and re-scales it to match the specified dimensions."""
    prim = add_usd_ref(stage, path, usd_path=box_asset_path)

    if DEBUG_INSPECT_MATERIALS:
        inspect_materials(stage, prim)
    convert_mdl_materials_to_preview(stage, prim, asset_dir=BOX_ASSET_DIR, verbose=False)

    rotate_x(prim, random.choice([-90, 0, 90, 180]))
    rotate_y(prim, random.choice([-90, 0, 90, 180]))

    usd_min, usd_max = compute_bbox(prim)

    usd_size = (
        usd_max[0] - usd_min[0],
        usd_max[1] - usd_min[1],
        usd_max[2] - usd_min[2]
    )

    required_scale = (
        size[0] / usd_size[0],
        size[1] / usd_size[1],
        size[2] / usd_size[2]
    )

    scale(prim, required_scale)
    return prim



def add_random_box_stack(
        stage,
        path: str,
        count_range=(1, 5),
        size_range=((30, 30, 10), (50, 50, 25)),
        angle_range=(-5, 5),
        jitter_range=(-3, 3)
    ):
    container = add_xform(stage, path)
    count = random.randint(*count_range)

    sizes = [
        (
            random.uniform(size_range[0][0], size_range[1][0]),
            random.uniform(size_range[0][1], size_range[1][1]),
            random.uniform(size_range[0][2], size_range[1][2])
        )
        for i in range(count)
    ]

    sizes = sorted(sizes, key=lambda x: x[0]**2 + x[1]**2, reverse=True)

    boxes = []
    for i in range(count):
        # OJO: paths de prims USD siempre con "/", nunca os.path.join
        box_i = add_box_of_size(stage, f"{path}/box_{i}", sizes[i])
        boxes.append(box_i)

    if count > 0:
        center = compute_bbox_center(boxes[0])
        for i in range(1, count):
            prev_box, cur_box = boxes[i - 1], boxes[i]
            cur_bbox = compute_bbox(cur_box)
            cur_center = compute_bbox_center(cur_box)
            prev_bbox = compute_bbox(prev_box)
            offset = (
                center[0] - cur_center[0],
                center[1] - cur_center[1],
                prev_bbox[1][2] - cur_bbox[0][2]
            )
            translate(cur_box, offset)

        for i in range(count):
            rotate_z(boxes[i], random.uniform(*angle_range))
            translate(boxes[i], (
                random.uniform(*jitter_range),
                random.uniform(*jitter_range),
                0
            ))
    return container, boxes


def add_random_box_stacks(stage, path: str, count_range=(0, 3)):
    container = add_xform(stage, path)
    stacks = []
    count = random.randint(*count_range)
    for i in range(count):
        stack, items = add_random_box_stack(stage, f"{path}/stack_{i}")
        stacks.append(stack)

    for i in range(count):
        cur_stack = stacks[i]
        cur_bbox = compute_bbox(cur_stack)
        cur_center = compute_bbox_center(cur_stack)
        translate(cur_stack, (0, -cur_center[1], -cur_bbox[0][2]))
        if i > 0:
            prev_bbox = compute_bbox(stacks[i - 1])
            translate(cur_stack, (prev_bbox[1][0] - cur_bbox[0][0], 0, 0))
    return container, stacks


def add_hand_truck_with_boxes(stage, path: str):
    container = add_xform(stage, path)

    hand_truck_path = f"{path}/truck"
    box_stacks_path = f"{path}/box_stacks"

    truck_prim = add_usd_ref(stage, hand_truck_path, hand_truck_asset_path)

    if DEBUG_INSPECT_MATERIALS:
        inspect_materials(stage, truck_prim)
    convert_mdl_materials_to_preview(stage, truck_prim, asset_dir=HAND_TRUCK_ASSET_DIR, verbose=False)

    box_stacks_container, box_stacks = add_random_box_stacks(
        stage, box_stacks_path, count_range=(1, 4))
    rotate_z(box_stacks_container, 90)

    translate(box_stacks_container, offset=(0, random.uniform(8, 12), 28))

    # remove out of bounds stacks
    last_visible = box_stacks[0]
    for i in range(len(box_stacks)):
        _, stack_bbox_max = compute_bbox(box_stacks[i])
        if stack_bbox_max[1] > 74:
            set_visibility(box_stacks[i], "invisible")
        else:
            last_visible = box_stacks[i]

    # wiggle inside bounds
    boxes_bbox = compute_bbox(last_visible)
    wiggle = (82 - boxes_bbox[1][1])
    translate(box_stacks_container, (0, random.uniform(0, wiggle), 1))
    return container


# ===========================================================================
# SECCION 4: Construccion de la escena completa (standalone, sin Omniverse)
# ===========================================================================

stage = new_in_memory_stage()

light = add_dome_light(stage, "/scene/dome_light")
floor = add_plane(stage, "/scene/floor", size=(1000, 1000), uv=(10, 10))

# Material estandar UsdPreviewSurface en lugar del MDL de Omniverse.
# Si tienes una textura de concreto: add_preview_material(..., texture_path=r"C:\...\concreto.jpg")
concrete = add_preview_material(
    stage,
    "/scene/materials/concrete",
    diffuse_color=(0.55, 0.55, 0.55),
    roughness=0.7,
)
bind_material(floor, concrete)

all_objects_container = add_xform(stage, "/scene/objects")
for i in range(5):
    for j in range(5):
        path = f"/scene/objects/hand_truck_{i}_{j}"
        current_object = add_hand_truck_with_boxes(stage, path)
        rotate_z(current_object, random.uniform(-15, 15))
        translate(current_object, (100 * i, 150 * j, 0))

objects_center = compute_bbox_center(all_objects_container)
translate(all_objects_container, (-objects_center[0], -objects_center[1], 0))

# Exportar a archivo (abre con: usdview escena_hand_trucks.usd)
export_stage(stage, OUTPUT_USD, default_prim="/scene")
print(f"Escena exportada a: {os.path.abspath(OUTPUT_USD)}")
