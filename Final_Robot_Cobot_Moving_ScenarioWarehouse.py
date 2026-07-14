import os
import sys
import math 
import random 

from pathlib import Path 
from typing import Tuple
from pxr import Usd,UsdShade, UsdGeom,Sdf,Gf, Kind,Vt

sys.path.insert(0, str(Path(__file__).parent))

from usd_scene_construction_utils import (
    add_usd_ref,
    rotate_x,
    rotate_y,
    rotate_z,
    scale,
    compute_bbox,
    add_xform,
    add_box,
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

#A.)Create the building

MAT_DEFS = {
    "Concrete":   dict(c=(0.52, 0.52, 0.53), r=0.85, m=0.0),
    "WallPanel":  dict(c=(0.86, 0.86, 0.84), r=0.70, m=0.0),
    "SteelDark":  dict(c=(0.10, 0.10, 0.11), r=0.55, m=0.9),
    "SteelLight": dict(c=(0.62, 0.63, 0.65), r=0.45, m=0.9),
    "Cardboard":  dict(c=(0.60, 0.45, 0.30), r=0.92, m=0.0),
    "CardboardB": dict(c=(0.68, 0.53, 0.36), r=0.92, m=0.0),
    "Wood":       dict(c=(0.56, 0.43, 0.28), r=0.88, m=0.0),
    "Wrap":       dict(c=(0.78, 0.82, 0.82), r=0.25, m=0.0, o=0.22),
    "Skylight":   dict(c=(0.90, 0.93, 0.96), r=0.30, m=0.0, e=(2.6, 2.7, 2.8)),
    "HiVis":      dict(c=(0.80, 0.92, 0.10), r=0.70, m=0.0, e=(0.10, 0.12, 0.01)),
    "Helmet":     dict(c=(0.92, 0.92, 0.90), r=0.35, m=0.0),
    "Skin":       dict(c=(0.72, 0.55, 0.44), r=0.70, m=0.0),
    "Trousers":   dict(c=(0.13, 0.14, 0.18), r=0.85, m=0.0),
    "RackBeam":   dict(c=(0.90, 0.68, 0.05), r=0.50, m=0.4),
    "RackPost":   dict(c=(0.10, 0.26, 0.60), r=0.50, m=0.4),
    "LineYellow": dict(c=(0.85, 0.72, 0.10), r=0.80, m=0.0),
}

MATS = {}

OUT = "building.usda"


#abrir o cerrar el patron idempotente
def open_or_create(path):
    if Usd.Stage.IsSupportedFile(path):
        layer = Sdf.Layer.FindOrOpen(path)
        if layer:
            layer.Clear()
            return Usd.Stage.Open(layer)
    return Usd.Stage.CreateNew(path)


#kit de lectura para el stage 
def dump(stage,title=""):
    print(f"\n --- Arbol {title}" + "-"*30)
    for prim in stage.Traverse():
        apis = prim.GetAppliedSchemas()
        extra = f"  apis={list(apis)}" if apis else ""
        print(f"  {'  ' * (prim.GetPath().pathElementCount - 1)}"
              f"{prim.GetName():<16} [{prim.GetTypeName() or '-'}]{extra}")
        
        
def show(stage,path):
    prim = stage.GetPrimAtPath(path)
    print(f"\n --- PRIM{path}"+"-"*30)
    
    if not prim.IsValid():
        print("No existe")
        return 
    
    print(f" tipo :  {prim.GetTypeName()}")
    print(f" padre : {prim.GetParent().GetPath()}")
    print(f" hijos : {[c.GetName() for c in prim.GetChildren()]}")
    print(f" es Cube? : {prim.IsA(UsdGeom.Cube)}")
    
    print(" Atributos autorados: ")
    for attr in prim.GetAttributes():
        if attr.HasAuthoredValue():
            print(f"    {attr.GetName():<22} = {attr.Get()}")
            
            
    #Leer un atributo concreto : 2 formas diferentes 
    if prim.IsA(UsdGeom.Cube):
        print(f" Size (generico) :{prim.GetAttribute('size').Get()}")
        print(f" Size (Tipado) :{UsdGeom.Cube(prim).GetSizeAttr().Get()}")
           
    # La transformacion : la lista de ops 
    xf = UsdGeom.Xformable(prim)
    if xf :
        print(" xformOps: ")
        for op in xf.GetOrderedXformOps():
            print(f"    {op.GetOpName():<22} = {op.Get()}")
        
        local = xf.GetLocalTransformation()
        world = UsdGeom.XformCache().GetLocalToWorldTransform(prim)
        print(f"  traslacion local : {local.ExtractTranslation()}")
        print(f"  traslacion mundo : {world.ExtractTranslation()}")

    #-- bbox ya transformado a mundo ? 
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
    r = cache.ComputeWorldBound(prim).ComputeAlignedRange()
    
    if not r.IsEmpty():
        print(f"  bbox mundo : {[round(v, 2) for v in r.GetMin()]} -> "
              f"{[round(v, 2) for v in r.GetMax()]}")
        
    mat = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()[0]
    
    if mat:
        print(f"  material : {mat.GetPath()}")
        
def find(stage,schema):
    return [p for p in stage.Traverse() if p.IsA(schema)]

def usda_text(stage):
    return stage.GetRootLayer().ExportToString()

#this is a canonical cube 
def box(path,size,pos,rot=None):
    c = UsdGeom.Cube.Define(stage,path)
    c.CreateSizeAttr(2.0)
    c.CreateExtentAttr(Vt.Vec3fArray([Gf.Vec3f(-1, -1, -1), Gf.Vec3f(1, 1, 1)]))
    c.AddTranslateOp().Set(Gf.Vec3d(*pos))
    
    if rot:
        c.AddRotateXYZOp().Set(Gf.Vec3f(*rot))
    c.AddScaleOp().Set(Gf.Vec3f(size[0] / 2, size[1] / 2, size[2] / 2))
    
    return c

def bind(prim, mat_name):
    """UsdShade.MaterialBindingAPI (schema aplicado, sin warnings)."""
    UsdShade.MaterialBindingAPI.Apply(prim).Bind(MATS[mat_name])


def poly(path, pts, mat):
    """UsdGeom.Mesh de un unico poligono (faldones de cubierta, hastiales)."""
    m = UsdGeom.Mesh.Define(stage, path)
    pv = Vt.Vec3fArray([Gf.Vec3f(*p) for p in pts])
    m.CreatePointsAttr(pv)
    m.CreateFaceVertexCountsAttr(Vt.IntArray([len(pts)]))
    m.CreateFaceVertexIndicesAttr(Vt.IntArray(list(range(len(pts)))))
    m.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    m.CreateExtentAttr(UsdGeom.PointBased(m).ComputeExtent(pv))
    bind(m.GetPrim(), mat)
    return m


def set_full_xform(prim, scale_factor, rot_x_deg, pos):
    """Aplica escala uniforme + rotacion en X + traslacion en un solo xformOp,
    sin depender del orden de llamadas de translate/scale/rotate_x (que reordenan
    xformOpOrder y pueden romper el calculo de posicion, ej. cuando la escala
    termina aplicandose despues de la traslacion)."""
    xf = UsdGeom.Xformable(prim)
    xf.ClearXformOpOrder()
    m_scale = Gf.Matrix4d(1.0).SetScale(scale_factor)
    m_rot = Gf.Matrix4d(1.0).SetRotate(Gf.Rotation(Gf.Vec3d(1, 0, 0), rot_x_deg))
    m_trans = Gf.Matrix4d(1.0).SetTranslate(Gf.Vec3d(*pos))
    combined = m_scale * m_rot * m_trans  # orden correcto: Scale -> Rotate -> Translate
    xf.AddTransformOp().Set(combined)

# A) Building size of the building
LEN_X , HALF_Y = 60.0,15.0 #this are in meters
EAVE_Z,RIDGE_Z = 6.0,9.0
WALL_T = 0.25

#Step one Stage
stage = open_or_create(OUT)

UsdGeom.SetStageUpAxis(stage,UsdGeom.Tokens.z)
UsdGeom.SetStageMetersPerUnit(stage,1.0)

world = UsdGeom.Xform.Define(stage,"/World")
stage.SetDefaultPrim(world.GetPrim())
#OpenUsd uses tokens
Usd.ModelAPI(world.GetPrim()).SetKind(Kind.Tokens.assembly)

print("Stage one")
print("  upAxis      :", UsdGeom.GetStageUpAxis(stage)) # Get the up axis?
print("  defaultPrim :", stage.GetDefaultPrim().GetPath())
dump(stage, "tras paso 1")


#defining materials
materials = UsdGeom.Scope.Define(stage, "/World/Materials")

# ---- Define materials once ----
floor_mat = add_preview_material(
    stage, "/World/Materials/WoodFloor",
    roughness=0.5,
    metallic=0.0,
    texture_path="./textures/wood.jpg",   # <-- tu imagen de madera
)

wall_mat = add_preview_material(
    stage, "/World/Materials/MarbleWall",
    roughness=0.3,
    metallic=0.0,
    texture_path="./textures/marble.jpg", # <-- tu imagen de marmol blanco
)

#Step two Solera
UsdGeom.Xform.Define(stage,"/World/Building")
#for example HALF_Y * 2 is because is simmetric ,
#usamos add_box (Mesh con UVs) en vez de box (Cube) porque el Cube no tiene
#coordenadas UV autoradas y la textura no se podria mapear correctamente
floor = add_box(stage, "/World/Building/Floor", (LEN_X + 2, HALF_Y * 2 + 2, 0.30))
translate(floor, (0, 0, -0.15))
print("\n Step 2 - Solera")
show(stage, "/World/Building/Floor")

cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
floor_top = cache.ComputeWorldBound(
    stage.GetPrimAtPath("/World/Building/Floor")).ComputeAlignedRange().GetMax()[2]
print(f"  -> la cota de apoyo para los muros es z = {floor_top}")

#Step Three Walls
# ---- Step Three Walls (Mesh con UVs, capture return values) ----
wall_yneg = add_box(stage, "/World/Building/Wall_Y_Neg", (LEN_X, WALL_T, EAVE_Z))
translate(wall_yneg, (0, -HALF_Y, EAVE_Z / 2))

wall_ypos = add_box(stage, "/World/Building/Wall_Y_Pos", (LEN_X, WALL_T, EAVE_Z))
translate(wall_ypos, (0, HALF_Y, EAVE_Z / 2))

wall_xneg = add_box(stage, "/World/Building/Wall_X_Neg", (WALL_T, HALF_Y * 2, EAVE_Z))
translate(wall_xneg, (-LEN_X / 2, 0, EAVE_Z / 2))

wall_xpos = add_box(stage, "/World/Building/Wall_X_Pos", (WALL_T, HALF_Y * 2, EAVE_Z))
translate(wall_xpos, (LEN_X / 2, 0, EAVE_Z / 2))


# ---- Bind materials ----
bind_material(floor, floor_mat)
bind_material(wall_yneg, wall_mat)
bind_material(wall_ypos, wall_mat)
bind_material(wall_xneg, wall_mat)
bind_material(wall_xpos, wall_mat)

print("\nPASO 3 — muros")
print("  meshes en el stage:", [p.GetName() for p in find(stage, UsdGeom.Mesh)])
dump(stage, "tras paso 3")

#Step Four , roof
B = "/World/Building"

# ---- Poblar MATS a partir de MAT_DEFS (antes de usar poly/bind) ----
for name, props in MAT_DEFS.items():
    MATS[name] = add_preview_material(
        stage, f"/World/Materials/{name}",
        diffuse_color=props["c"],
        roughness=props["r"],
        metallic=props["m"],
    )

# ---- Faldones del techo (los dos planos inclinados, alero -> cumbrera) ----
poly(f"{B}/RoofSlope_Pos", [
    (-LEN_X / 2,  HALF_Y, EAVE_Z),
    ( LEN_X / 2,  HALF_Y, EAVE_Z),
    ( LEN_X / 2,        0, RIDGE_Z),
    (-LEN_X / 2,        0, RIDGE_Z),
], "SteelLight")

poly(f"{B}/RoofSlope_Neg", [
    (-LEN_X / 2, -HALF_Y, EAVE_Z),
    ( LEN_X / 2, -HALF_Y, EAVE_Z),
    ( LEN_X / 2,        0, RIDGE_Z),
    (-LEN_X / 2,        0, RIDGE_Z),
], "SteelLight")

# ---- Hastiales (triangulos en los extremos X) ----
for sgn,tag in ((-1,"Neg"),(1,"Pos")):
    x = sgn*LEN_X/2
    poly(f"{B}/Gable_{tag}", [(x, -HALF_Y, EAVE_Z), (x, HALF_Y, EAVE_Z), (x, 0, RIDGE_Z)],
         "WallPanel")

print("\nPASO 4 — techo")
print("  meshes en el stage:", [p.GetName() for p in find(stage, UsdGeom.Mesh)])
dump(stage, "tras paso 4")

#Step Five , storage rack (centrado en el edificio)
rack = add_usd_ref(stage, "/World/Building/StorageRack", "./Storage Rack.usdc")

x_min_int, x_max_int = -LEN_X/2 + WALL_T/2, LEN_X/2 - WALL_T/2
y_min_int, y_max_int = -HALF_Y + WALL_T/2, HALF_Y - WALL_T/2

bmin, bmax = compute_bbox(rack)
center_x = (bmin[0] + bmax[0]) / 2
center_y = (bmin[1] + bmax[1]) / 2
rack_half_x = (bmax[0] - bmin[0]) / 2

target_x_rack = 0   # centro del edificio en X
target_y_rack = 0   # centro del edificio en Y

translate(rack, (target_x_rack - center_x, target_y_rack - center_y, floor_top - bmin[2]))
print("\nPASO 5 — storage rack")
show(stage, "/World/Building/StorageRack")

#Step Six , AMR / cobot (una sola transformacion combinada, sin ambiguedad de orden)
amr = add_usd_ref(stage, "/World/Building/AMR_Cobot", "./UR__Cobot_Mir_AMR.usdz")

# 1) medir el asset SIN transformar (recien referenciado, identidad)
bmin0, bmax0 = compute_bbox(amr)
size0 = (bmax0[0] - bmin0[0], bmax0[1] - bmin0[1], bmax0[2] - bmin0[2])
factor_escala = 1.6 / max(size0)   # normaliza a ~1.6 m en su dimension mayor

# 2) aplicar temporalmente solo escala + rotacion (sin traslacion) para medir el bbox ya orientado
set_full_xform(amr, factor_escala, 90, (0, 0, 0))
bmin1, bmax1 = compute_bbox(amr)
center_x1 = (bmin1[0] + bmax1[0]) / 2
center_y1 = (bmin1[1] + bmax1[1]) / 2

# 3) calcular la traslacion final: centrado en el punto deseado + apoyado en el piso
gap = 0.3  # metros de pasillo entre el rack y el robot (reducido: el brazo solo alcanza ~0.9m)
target_x_amr = target_x_rack + rack_half_x + gap
target_y_amr = target_y_rack

dx = target_x_amr - center_x1
dy = target_y_amr - center_y1
dz = floor_top - bmin1[2]

# 4) aplicar la transformacion final completa de una sola vez
set_full_xform(amr, factor_escala, 90, (dx, dy, dz))

print("\nPASO 6 — AMR/cobot")
show(stage, "/World/Building/AMR_Cobot")

#Step Six-B , caja individual escalada para el gripper (copia independiente del rack)

# 0) ubicar los joints del brazo ANTES de elegir caja: la caja debe elegirse por
#    distancia 3D real al HOMBRO del brazo (Joint_001), no por distancia XY al
#    centro del AMR -- el hombro no esta centrado en el AMR y ademas la altura
#    de cada estante importa mucho (el brazo mide menos de 1m de alcance total).
GRIPPER_BASE = ("/World/Building/AMR_Cobot/ref/Meshes/Sketchfab_model/root/"
    "GLTF_SceneRootNode/Universal_robots_ur5e_with_on_robot_two_finger_gripper_RG2__16")
J1 = stage.GetPrimAtPath(f"{GRIPPER_BASE}/Joint_001_15")
J2 = stage.GetPrimAtPath(f"{GRIPPER_BASE}/Joint_001_15/Bow_001_13/Joint_002_12")
J3 = stage.GetPrimAtPath(f"{GRIPPER_BASE}/Joint_001_15/Bow_001_13/Joint_002_12/Bow_002_10/Joint_003_9")
GRIP = stage.GetPrimAtPath(f"{GRIPPER_BASE}/Joint_001_15/Bow_001_13/Joint_002_12/Bow_002_10/"
    "Joint_003_9/Bow_003_7/Joint_004_6/wrist_5/Claw_brecket_3")

def world_pos(prim):
    m = UsdGeom.XformCache().GetLocalToWorldTransform(prim)
    return m.Transform(Gf.Vec3d(0, 0, 0))

p1 = world_pos(J1)
p2 = world_pos(J2)
p3 = world_pos(J3)
pg = world_pos(GRIP)
L1 = (p2 - p1).GetLength()   # eslabon hombro -> codo
L2 = (p3 - p2).GetLength()   # eslabon codo -> muñeca
L3 = (pg - p3).GetLength()   # muñeca -> punta del gripper
ARM_REACH = L1 + L2 + L3

print(f"\n  brazo: L1={L1:.3f} L2={L2:.3f} L3={L3:.3f} alcance_max={ARM_REACH:.3f}")

# 1) buscar automaticamente la caja "dus_XXX" del rack MAS CERCANA al hombro del
#    brazo EN 3D, priorizando las que caen dentro del alcance real (85% del maximo,
#    para no exigir extension total/singularidad)
rack_root = stage.GetPrimAtPath("/World/Building/StorageRack/ref")

def _find_nearest_box(max_reach):
    best_name_, best_d_ = None, None
    for child in rack_root.GetChildren():
        if not child.GetName().startswith("dus_"):
            continue
        cmin, cmax = compute_bbox(child)
        cx, cy, cz = (cmin[0]+cmax[0])/2, (cmin[1]+cmax[1])/2, (cmin[2]+cmax[2])/2
        d3 = ((cx-p1[0])**2 + (cy-p1[1])**2 + (cz-p1[2])**2) ** 0.5
        if max_reach is not None and d3 > max_reach:
            continue
        if best_d_ is None or d3 < best_d_:
            best_d_, best_name_ = d3, child.GetName()
    return best_name_, best_d_

best_name, best_dist3 = _find_nearest_box(ARM_REACH * 0.85)
if best_name is None:
    print("  !! ninguna caja dentro del 85% del alcance, uso la mas cercana sin filtrar")
    best_name, best_dist3 = _find_nearest_box(None)

print(f"  -> caja alcanzable mas cercana al hombro del brazo: {best_name} (dist3D={best_dist3:.3f})")

# IMPORTANTE: la referencia va en un prim HIJO ("ref"), igual que add_usd_ref,
# para no pisar con set_full_xform la escala de fabrica que trae la caja
# (esa escala es la que encoge la malla generica 2x2x2 al tamaño real de la caja).
demo_box = UsdGeom.Xform.Define(stage, "/World/Building/DemoBox")
demo_box_ref = stage.DefinePrim("/World/Building/DemoBox/ref")
demo_box_ref.GetReferences().AddReference("./Storage Rack.usdc", f"/root/{best_name}")

# 1) medir sin transformar y calcular el factor de escala
bmin_b0, bmax_b0 = compute_bbox(demo_box.GetPrim())
size_b0 = (bmax_b0[0]-bmin_b0[0], bmax_b0[1]-bmin_b0[1], bmax_b0[2]-bmin_b0[2])
factor_escala_caja = 0.08 / min(size_b0)   # dimension mas angosta -> 8cm, calza en el gripper (max 11cm)

# 2) aplicar solo la escala (sin traslacion) para medir el bbox ya escalado
set_full_xform(demo_box.GetPrim(), factor_escala_caja, 0, (0, 0, 0))
bmin_b1, bmax_b1 = compute_bbox(demo_box.GetPrim())
center_xb = (bmin_b1[0] + bmax_b1[0]) / 2
center_yb = (bmin_b1[1] + bmax_b1[1]) / 2

# 3) colocarla en el MISMO estante donde esa caja esta realmente puesta en el rack
#    (medimos su posicion actual, YA con el translate del rack aplicado)
shelf_slot = stage.GetPrimAtPath(f"/World/Building/StorageRack/ref/{best_name}")
smin, smax = compute_bbox(shelf_slot)
target_x_demo = (smin[0] + smax[0]) / 2
target_y_demo = (smin[1] + smax[1]) / 2
shelf_z = smin[2]   # altura de la superficie del estante donde esa caja se apoya

dx_b = target_x_demo - center_xb
dy_b = target_y_demo - center_yb
dz_b = shelf_z - bmin_b1[2]

set_full_xform(demo_box.GetPrim(), factor_escala_caja, 0, (dx_b, dy_b, dz_b))

# guardamos esta pose "en el estante" ANTES de que el paso 7 la sobreescriba,
# la necesitamos como primer keyframe de la animacion (paso 8)
BOX_SHELF_XFORM = UsdGeom.Xformable(demo_box.GetPrim()).GetLocalTransformation()
_bmn_flat, _bmx_flat = compute_bbox(demo_box.GetPrim())
BOX_FLAT_HEIGHT = _bmx_flat[2] - _bmn_flat[2]   # alto de la caja "acostada" sobre una cara,
                                                  # sin rotacion -- se usa en el paso 8 para
                                                  # que quede apoyada plana, no hundida/chueca

# ocultar la caja grande original de ese slot para que no se superponga con la version chica
if shelf_slot.IsValid():
    set_visibility(shelf_slot, "invisible")

bmin_b, bmax_b = compute_bbox(demo_box.GetPrim())
print("\nPASO 6B — caja demo (escalada para el gripper, en el estante mas cercano al AMR)")
print("  tamaño final:", [round(bmax_b[i]-bmin_b[i], 3) for i in range(3)])
print("  posicion:", [round((bmin_b[i]+bmax_b[i])/2, 3) for i in range(3)])
print("  distancia 3D al hombro del brazo:", round(best_dist3, 3), "m")
show(stage, "/World/Building/DemoBox")

#Step 7 , cinematica inversa NUMERICA con EVASION DE COLISION (busqueda de eje+angulo
# por joint, penalizando poses donde el brazo atraviesa las vigas del rack).
#
# NOTA: no sabemos el eje de rotacion local real de cada joint (es una malla
# decorativa de Sketchfab, matrices ya combinadas, no un rig con convencion
# documentada). En vez de adivinar un eje fijo (X/Y/Z) y fallar, probamos muchas
# direcciones de eje candidatas (no solo cardinales) y afinamos con descenso por
# coordenadas, minimizando distancia + colisiones. Tarda unos segundos extra en
# correr, pero no depende de adivinar nada.
import random as _random

orig_joint_xf = {
    J1.GetPath(): UsdGeom.Xformable(J1).GetLocalTransformation(),
    J2.GetPath(): UsdGeom.Xformable(J2).GetLocalTransformation(),
    J3.GetPath(): UsdGeom.Xformable(J3).GetLocalTransformation(),
}

def set_joint_rotation(prim, axis, angle_deg):
    """Agrega una rotacion sobre la matriz local ORIGINAL del joint (rota alrededor
    de su propio pivote, conservando su orientacion/posicion de fabrica)."""
    xfj = UsdGeom.Xformable(prim)
    r = Gf.Matrix4d(1.0).SetRotate(Gf.Rotation(axis, angle_deg))
    xfj.ClearXformOpOrder()
    xfj.AddTransformOp().Set(r * orig_joint_xf[prim.GetPath()])

bmin_t, bmax_t = compute_bbox(demo_box.GetPrim())
target = Gf.Vec3d((bmin_t[0]+bmax_t[0])/2, (bmin_t[1]+bmax_t[1])/2, (bmin_t[2]+bmax_t[2])/2)

# ---- modelo de colision: bandas de altura de las vigas, medidas de la malla real ----
def _get_rack_beam_bands():
    mez_candidates = [c for c in rack_root.GetChildren() if c.GetName().startswith("mezanine")]
    if not mez_candidates:
        return []
    mesh_children = [c for c in mez_candidates[0].GetChildren() if c.GetTypeName() == "Mesh"]
    if not mesh_children:
        return []
    m = UsdGeom.Mesh(mesh_children[0])
    pts = m.GetPointsAttr().Get()
    if not pts:
        return []
    world_m = UsdGeom.XformCache().GetLocalToWorldTransform(mesh_children[0])
    zs = sorted(world_m.Transform(p)[2] for p in pts)
    bands, band_start, prev = [], zs[0], zs[0]
    for z in zs[1:]:
        if z - prev > 0.1:
            bands.append((band_start, prev))
            band_start = z
        prev = z
    bands.append((band_start, prev))
    return bands

BEAM_BANDS = _get_rack_beam_bands()
rack_bmin, rack_bmax = compute_bbox(rack)
RACK_XMIN, RACK_XMAX = rack_bmin[0], rack_bmax[0]
RACK_YMIN, RACK_YMAX = rack_bmin[1], rack_bmax[1]
print(f"\n  bandas de vigas detectadas: {len(BEAM_BANDS)}")

# ---- modelo de colision: postes/paneles VERTICALES del rack (las bandas de arriba solo
# cubren vigas horizontales; un poste/panel vertical entre dos estantes queda en el "hueco"
# entre bandas y el brazo podia atravesarlo sin que se detectara). Los 12 modulos
# 'mezanine_racking_XXX' son de DOS tipos: unos son vigas/estantes (material anaranjado,
# ya cubiertos por BEAM_BANDS) y otros son postes/paneles solidos verticales (material
# AZUL). Se distinguen por el COLOR del material (azul dominante), no por el nombre,
# para no depender de una convencion especifica de este asset.
def _get_rack_post_obstacles():
    boxes = []
    for mod in rack_root.GetChildren():
        if not mod.GetName().startswith("mezanine"):
            continue
        mesh_children = [c for c in mod.GetChildren() if c.GetTypeName() == "Mesh"]
        if not mesh_children:
            continue
        mesh_prim = mesh_children[0]
        mat, _ = UsdShade.MaterialBindingAPI(mesh_prim).ComputeBoundMaterial()
        color = None
        if mat:
            for shader_prim in Usd.PrimRange(mat.GetPrim()):
                if shader_prim.IsA(UsdShade.Shader):
                    inp = UsdShade.Shader(shader_prim).GetInput("diffuseColor")
                    if inp:
                        v = inp.Get()
                        if v is not None:
                            color = v
        is_post = color is not None and color[2] > color[0] * 1.5 and color[2] > color[1] * 1.5
        if is_post:
            bmn, bmx = compute_bbox(mesh_prim)
            boxes.append((bmn[0], bmx[0], bmn[1], bmx[1], bmn[2], bmx[2]))
    return boxes

RACK_POSTS = _get_rack_post_obstacles()
print(f"  postes/paneles verticales detectados: {len(RACK_POSTS)}")

# obstaculos adicionales que se van agregando mas adelante (ej. la plataforma del
# AMR en el paso 8, para que el brazo no se hunda ahi al colocar la caja). Vacia
# por ahora -- _count_collisions ya la revisa, se llena despues sin tener que
# redefinir la funcion.
EXTRA_OBSTACLES = []

def _segment_hits_box(p_a, p_b, xmin, xmax, ymin, ymax, zmin, zmax):
    """Test de interseccion segmento-vs-caja (slab method)."""
    d = [p_b[i] - p_a[i] for i in range(3)]
    tmin, tmax = 0.0, 1.0
    bounds = [(xmin, xmax), (ymin, ymax), (zmin, zmax)]
    for i in range(3):
        lo, hi = bounds[i]
        if abs(d[i]) < 1e-9:
            if p_a[i] < lo or p_a[i] > hi:
                return False
        else:
            t1, t2 = (lo - p_a[i]) / d[i], (hi - p_a[i]) / d[i]
            if t1 > t2:
                t1, t2 = t2, t1
            tmin, tmax = max(tmin, t1), min(tmax, t2)
            if tmin > tmax:
                return False
    return True

# margen de seguridad: el gripper y la caja tienen volumen real (no son puntos/lineas
# de ancho cero como los segmentos del test de colision), asi que sin este margen el
# solver puede acercarse tanto a una viga que el gripper/caja terminan visualmente
# "hundidos" en ella aunque el segmento central no la cruce. Se infla cada banda de
# viga hacia arriba y abajo por este valor antes de probar interseccion.
COLLISION_MARGIN = 0.06  # metros (~ mitad del ancho de la caja/gripper)

def _count_collisions(pa, pb, pc, pd):
    """Cuenta cuantos de los 3 eslabones del brazo cruzan alguna viga horizontal,
    algun poste/panel vertical del rack, o algun obstaculo extra (ej. la plataforma
    del AMR, agregada en el paso 8) -- con margen de seguridad para dar espacio al
    volumen real del gripper/caja."""
    hits = 0
    for a, b in ((pa, pb), (pb, pc), (pc, pd)):
        for zmin, zmax in BEAM_BANDS:
            if _segment_hits_box(a, b, RACK_XMIN, RACK_XMAX, RACK_YMIN, RACK_YMAX,
                                  zmin - COLLISION_MARGIN, zmax + COLLISION_MARGIN):
                hits += 1
        for xmin, xmax, ymin, ymax, zmin, zmax in RACK_POSTS:
            if _segment_hits_box(a, b,
                                  xmin - COLLISION_MARGIN, xmax + COLLISION_MARGIN,
                                  ymin - COLLISION_MARGIN, ymax + COLLISION_MARGIN,
                                  zmin - COLLISION_MARGIN, zmax + COLLISION_MARGIN):
                hits += 1
        for xmin, xmax, ymin, ymax, zmin, zmax in EXTRA_OBSTACLES:
            # OJO: aqui NO se infla el techo (zmax) con el margen -- estos obstaculos
            # representan una superficie de apoyo (ej. la plataforma del AMR) y el
            # punto objetivo esta justo encima de esa superficie; si se inflara zmax
            # tambien, el margen chocaria con el propio objetivo y nunca convergeria
            # a 0 colisiones. Solo se da margen en XY (para no rozar los bordes) y
            # hacia abajo (zmin), no hacia arriba.
            if _segment_hits_box(a, b,
                                  xmin - COLLISION_MARGIN, xmax + COLLISION_MARGIN,
                                  ymin - COLLISION_MARGIN, ymax + COLLISION_MARGIN,
                                  zmin - COLLISION_MARGIN, zmax):
                hits += 1
    return hits

_random.seed(7)
def _random_axes(n):
    out = []
    for _ in range(n):
        v = Gf.Vec3d(_random.gauss(0, 1), _random.gauss(0, 1), _random.gauss(0, 1))
        out.append(v.GetNormalized())
    return out

best_pose = {J1: (Gf.Vec3d(0, 1, 0), 0.0), J2: (Gf.Vec3d(0, 0, 1), 0.0), J3: (Gf.Vec3d(0, 0, 1), 0.0)}

def _apply_pose():
    for j, (ax, ang) in best_pose.items():
        set_joint_rotation(j, ax, ang)

def _positions():
    _apply_pose()
    return world_pos(J1), world_pos(J2), world_pos(J3), world_pos(GRIP)

def _cost():
    pp1, pp2, pp3, pg = _positions()
    d = (pg - target).GetLength()
    c = _count_collisions(pp1, pp2, pp3, pg)
    return d + c * 4.0   # penalizacion fuerte por cada eslabon en colision (con margen)

# limites articulares aproximados (grados), para que la pose se vea mas como un
# brazo real y no se doble en angulos extremos/antinaturales. J1 (base) puede
# girar mas amplio; J2/J3 (hombro/codo) se restringen mas.
ANGLE_LIMIT_DEG = {J1: 160.0, J2: 130.0, J3: 130.0}

print(f"PASO 7 — buscando pose del brazo (cost inicial={_cost():.3f})...")
axes_pool = _random_axes(40)
for round_i in range(8):
    for joint in (J1, J2, J3):
        limit = ANGLE_LIMIT_DEG[joint]
        best_local, best_c = best_pose[joint], None
        for axis in axes_pool + [best_pose[joint][0]]:
            for ang10 in range(int(-limit*10), int(limit*10)+1, 15):
                ang = ang10 / 10.0
                best_pose[joint] = (axis, ang)
                c = _cost()
                if best_c is None or c < best_c:
                    best_c, best_local = c, (axis, ang)
        best_pose[joint] = best_local
    axes_pool = _random_axes(20) + [best_pose[J1][0], best_pose[J2][0], best_pose[J3][0]]
    print(f"  ronda {round_i}: cost={_cost():.4f}")

pp1, pp2, pp3, pg = _positions()
final_dist = (pg - target).GetLength()
final_collisions = _count_collisions(pp1, pp2, pp3, pg)
print(f"PASO 7 — distancia final gripper-caja = {final_dist:.3f} m,  colisiones = {final_collisions}")

# mover la caja a la posicion FINAL real del gripper, ya con el brazo doblado,
# Y copiarle la ROTACION del gripper (si no, la caja queda con la orientacion
# que tenia en el estante -> se ve "chueca" en vez de alineada con las pinzas).
#
# IMPORTANTE: cambiar la rotacion cambia la relacion entre el pivote del objeto
# y el centro de su bbox -- por eso hay que aplicar escala+rotacion PRIMERO (sin
# traslacion), medir donde quedo el centro CON esa nueva orientacion, y recien
# ahi calcular la traslacion necesaria (mismo patron de 2 fases que set_full_xform).

# 1) extraer SOLO la rotacion del gripper (sin su escala/traslacion acumulada)
grip_world = UsdGeom.XformCache().GetLocalToWorldTransform(GRIP)
grip_rot_only = grip_world.RemoveScaleShear()
grip_rot3 = grip_rot_only.ExtractRotationMatrix()

m_scale = Gf.Matrix4d(1.0).SetScale(factor_escala_caja)
m_rot = Gf.Matrix4d(grip_rot3, Gf.Vec3d(0, 0, 0))

xf_box = UsdGeom.Xformable(demo_box.GetPrim())
xf_box.ClearXformOpOrder()
xf_box.AddTransformOp().Set(m_scale * m_rot)   # sin traslacion todavia

# 2) medir donde quedo el centro del bbox YA con la nueva rotacion aplicada
bmin_h, bmax_h = compute_bbox(demo_box.GetPrim())
center_h = Gf.Vec3d((bmin_h[0]+bmax_h[0])/2, (bmin_h[1]+bmax_h[1])/2, (bmin_h[2]+bmax_h[2])/2)

gmin, gmax = compute_bbox(GRIP)
grip_center = Gf.Vec3d((gmin[0]+gmax[0])/2, (gmin[1]+gmax[1])/2, (gmin[2]+gmax[2])/2)

needed_translate = grip_center - center_h

# 3) aplicar la transformacion final completa de una sola vez
m_trans = Gf.Matrix4d(1.0).SetTranslate(needed_translate)
xf_box.ClearXformOpOrder()
xf_box.AddTransformOp().Set(m_scale * m_rot * m_trans)

print("PASO 7 — brazo posicionado, caja siguiendo al gripper (posicion + rotacion)")
show(stage, "/World/Building/DemoBox")

#Step 8 , animacion: brazo en reposo -> alcanza la caja -> la agarra -> la lleva
# al area verde de colocacion del AMR ("mask_placment") -> la suelta -> vuelve a
# reposo. Reutiliza la misma busqueda numerica del paso 7 (mismos limites de
# angulo y evasion de colision) para encontrar la pose de "colocar", y en vez de
# saltar directo a la pose final, graba varios frames intermedios (interpolando
# la ROTACION de cada joint con slerp) para que el movimiento se vea continuo.

FPS = 24
F_START, F_REACH, F_GRAB_HOLD = 0, 30, 40
F_PLACE, F_RELEASE, F_RETURN = 90, 100, 130
STEP = 5

print("\nPASO 8 — animacion (agarrar caja y colocarla en el area verde del AMR)")

# 1) localizar el area verde ("mask_placment") en el AMR ya colocado, para saber
#    donde soltar la caja. Se identifico por inspeccion directa del asset: es una
#    malla llamada 'mask_placment_59' con un material verde oscuro (Object_146).
AMR_ROOT = "/World/Building/AMR_Cobot/ref"
GREEN_AREA = stage.GetPrimAtPath(
    f"{AMR_ROOT}/Meshes/Sketchfab_model/root/GLTF_SceneRootNode/mask_placment_59/Object_146")

if GREEN_AREA.IsValid():
    gmin_a, gmax_a = compute_bbox(GREEN_AREA)
    pad_top_z = gmax_a[2]
    place_target = Gf.Vec3d((gmin_a[0] + gmax_a[0]) / 2,
                             (gmin_a[1] + gmax_a[1]) / 2,
                             pad_top_z + 0.06)  # un poco por encima de la superficie (objetivo del GRIPPER)
    print(f"  area verde encontrada, objetivo de colocacion: {[round(v,3) for v in place_target]}")
else:
    # respaldo: encima del cuerpo del AMR, por si el nombre del prim cambia entre versiones del asset
    amr_bmin, amr_bmax = compute_bbox(amr)
    pad_top_z = amr_bmax[2]
    place_target = Gf.Vec3d((amr_bmin[0] + amr_bmax[0]) / 2,
                             (amr_bmin[1] + amr_bmax[1]) / 2,
                             pad_top_z + 0.06)
    print("  !! no se encontro 'mask_placment_59/Object_146', uso el centro superior del AMR")

# 1b) la plataforma del AMR (donde va el area verde) tambien es un obstaculo solido --
# sin esto, la busqueda numerica solo intenta acercar el GRIPPER al punto objetivo y
# puede terminar hundiendo el brazo/gripper dentro del cuerpo del robot para llegar a
# el, ya que nada le impedia pasar por debajo de la superficie de la plataforma. Se
# agrega un bloque solido desde el piso hasta la superficie del area verde, acotado al
# area (con un margen) para no chocar con nada fuera de esa zona (ej. el propio hombro
# del brazo, que esta en otra parte del AMR).
AMR_PAD_MARGIN = 0.15
AMR_PLATFORM = (gmin_a[0] - AMR_PAD_MARGIN if GREEN_AREA.IsValid() else place_target[0] - 0.3,
                gmax_a[0] + AMR_PAD_MARGIN if GREEN_AREA.IsValid() else place_target[0] + 0.3,
                gmin_a[1] - AMR_PAD_MARGIN if GREEN_AREA.IsValid() else place_target[1] - 0.3,
                gmax_a[1] + AMR_PAD_MARGIN if GREEN_AREA.IsValid() else place_target[1] + 0.3,
                floor_top, pad_top_z)
EXTRA_OBSTACLES.append(AMR_PLATFORM)
print(f"  plataforma del AMR agregada como obstaculo (hasta z={round(pad_top_z,3)})")

# 2) guardar la pose de "agarre" (la que dejo el paso 7 en best_pose) y buscar,
#    partiendo de ahi, la pose que deja el gripper sobre el area verde
grab_pose = {j: v for j, v in best_pose.items()}

target = place_target   # _cost()/_positions() usan la variable global "target"
best_pose = {j: v for j, v in grab_pose.items()}   # arrancar la busqueda desde la pose de agarre

print(f"  buscando pose de colocacion (cost inicial={_cost():.3f})...")
axes_pool = _random_axes(40)
for round_i in range(8):
    for joint in (J1, J2, J3):
        limit = ANGLE_LIMIT_DEG[joint]
        best_local, best_c = best_pose[joint], None
        for axis in axes_pool + [best_pose[joint][0]]:
            for ang10 in range(int(-limit * 10), int(limit * 10) + 1, 15):
                ang = ang10 / 10.0
                best_pose[joint] = (axis, ang)
                c = _cost()
                if best_c is None or c < best_c:
                    best_c, best_local = c, (axis, ang)
        best_pose[joint] = best_local
    axes_pool = _random_axes(20) + [best_pose[J1][0], best_pose[J2][0], best_pose[J3][0]]
    print(f"    ronda {round_i}: cost={_cost():.4f}")

place_pose = {j: v for j, v in best_pose.items()}
pp1, pp2, pp3, pg = _positions()
print(f"  distancia final gripper-area verde = {(pg - target).GetLength():.3f} m,"
      f"  colisiones = {_count_collisions(pp1, pp2, pp3, pg)}")

rest_pose = {J1: (Gf.Vec3d(0, 1, 0), 0.0), J2: (Gf.Vec3d(0, 0, 1), 0.0), J3: (Gf.Vec3d(0, 0, 1), 0.0)}

# 3) attrs directos (sin pasar por Add/ClearXformOpOrder) para grabar time samples
#    sin arriesgarnos a duplicar entradas en xformOpOrder
attr_j1 = J1.GetAttribute("xformOp:transform")
attr_j2 = J2.GetAttribute("xformOp:transform")
attr_j3 = J3.GetAttribute("xformOp:transform")
attr_box = demo_box.GetPrim().GetAttribute("xformOp:transform")

# transform "asentada": la caja PLANA (sin la rotacion arbitraria del gripper),
# apoyada exactamente sobre la superficie del area verde. Se usa como destino final
# al soltar, para que no quede ni hundida ni chueca.
attr_box.Set(Gf.Matrix4d(1.0).SetScale(factor_escala_caja), Usd.TimeCode.Default())
_bmn_s, _bmx_s = compute_bbox(demo_box.GetPrim())
_center_s = Gf.Vec3d((_bmn_s[0] + _bmx_s[0]) / 2, (_bmn_s[1] + _bmx_s[1]) / 2, (_bmn_s[2] + _bmx_s[2]) / 2)
settled_center = Gf.Vec3d(place_target[0], place_target[1], pad_top_z + BOX_FLAT_HEIGHT / 2)
m_settled = (Gf.Matrix4d(1.0).SetScale(factor_escala_caja) *
             Gf.Matrix4d(1.0).SetTranslate(settled_center - _center_s))

def _interp_pose(pose_a, pose_b, t):
    """Interpola la ROTACION de cada joint entre dos poses via slerp de cuaterniones
    (evita el problema de que cada pose puede usar un eje distinto)."""
    out = {}
    for j in (J1, J2, J3):
        qa = Gf.Rotation(*pose_a[j]).GetQuat()
        qb = Gf.Rotation(*pose_b[j]).GetQuat()
        q = Gf.Slerp(t, qa, qb)
        r = Gf.Rotation(q)
        out[j] = (r.axis, r.angle)
    return out

def _refine_pose_for_collision(pose, window=60.0, step=15.0, rounds=2):
    """Ajuste local (mismo eje, solo se mueve el angulo dentro de una ventana chica)
    para que un frame INTERMEDIO de la animacion no atraviese una viga/poste que
    ninguna de las dos poses extremas (agarre/colocar) tocaba -- el paso 7/8 solo
    valida las poses finales, no el camino interpolado entre ellas."""
    cur = {j: v for j, v in pose.items()}
    for j, (axis, ang) in cur.items():
        best_pose[j] = (axis, ang)
    pp1, pp2, pp3, pg = _positions()
    if _count_collisions(pp1, pp2, pp3, pg) == 0:
        return cur
    for _ in range(rounds):
        for j in (J1, J2, J3):
            axis0, ang0 = cur[j]
            best_local, best_c = (axis0, ang0), None
            for d in range(int(-window), int(window) + 1, int(step)):
                ang = ang0 + d
                best_pose[j] = (axis0, ang)
                pp1, pp2, pp3, pg = _positions()
                c = _count_collisions(pp1, pp2, pp3, pg)
                penalty = c * 10.0 + abs(d) * 0.002   # preferir el menor desvio si hay empate
                if best_c is None or penalty < best_c:
                    best_c, best_local = penalty, (axis0, ang)
            cur[j] = best_local
            best_pose[j] = best_local
    return cur

def _write_pose_frame(pose, frame, avoid_collision=True):
    if avoid_collision:
        pose = _refine_pose_for_collision(pose)
    for j, (axis, ang) in pose.items():
        set_joint_rotation(j, axis, ang)   # escribe el valor default (usa la utilidad ya probada)
    for j, attr in ((J1, attr_j1), (J2, attr_j2), (J3, attr_j3)):
        local = UsdGeom.Xformable(j).GetLocalTransformation()
        attr.Set(local, Usd.TimeCode(frame))
    return pose

def _write_box_follow_frame(frame, settle_w=0.0):
    """Caja alineada y centrada en el gripper resultante de la pose YA escrita
    (mismo patron de 2 fases que al final del paso 7). Si settle_w > 0, mezcla
    (posicion + rotacion, con slerp) hacia la pose 'asentada' (m_settled) para que
    al soltarla en el area verde quede plana y apoyada, no hundida ni chueca."""
    grip_world = UsdGeom.XformCache().GetLocalToWorldTransform(GRIP)
    rot_g = grip_world.RemoveScaleShear().ExtractRotation()
    m_s = Gf.Matrix4d(1.0).SetScale(factor_escala_caja)
    m_r = Gf.Matrix4d(1.0).SetRotate(rot_g)

    attr_box.Set(m_s * m_r, Usd.TimeCode.Default())
    bmn, bmx = compute_bbox(demo_box.GetPrim())
    c = Gf.Vec3d((bmn[0] + bmx[0]) / 2, (bmn[1] + bmx[1]) / 2, (bmn[2] + bmx[2]) / 2)
    gmn, gmx = compute_bbox(GRIP)
    gc = Gf.Vec3d((gmn[0] + gmx[0]) / 2, (gmn[1] + gmx[1]) / 2, (gmn[2] + gmx[2]) / 2)
    m_follow = m_s * m_r * Gf.Matrix4d(1.0).SetTranslate(gc - c)

    if settle_w <= 0.0:
        m_out = m_follow
    elif settle_w >= 1.0:
        m_out = m_settled
    else:
        t_follow = m_follow.ExtractTranslation()
        t_settled = m_settled.ExtractTranslation()
        t = t_follow * (1 - settle_w) + t_settled * settle_w
        q_follow = m_follow.ExtractRotation().GetQuat()
        q_settled = m_settled.ExtractRotation().GetQuat()
        q = Gf.Slerp(settle_w, q_follow, q_settled)
        m_out = (Gf.Matrix4d(1.0).SetScale(factor_escala_caja) *
                 Gf.Matrix4d(1.0).SetRotate(Gf.Rotation(q)) *
                 Gf.Matrix4d(1.0).SetTranslate(t))

    attr_box.Set(m_out, Usd.TimeCode(frame))
    return m_out

def _animate_segment(pose_a, pose_b, f_a, f_b, box_follow=False, settle_start=None):
    frame = f_a
    last_box_xform = None
    while True:
        t = 0.0 if f_b == f_a else (frame - f_a) / (f_b - f_a)
        pose_t = _interp_pose(pose_a, pose_b, t)
        _write_pose_frame(pose_t, frame)
        if box_follow:
            if settle_start is not None and frame > settle_start:
                settle_w = (frame - settle_start) / (f_b - settle_start)
            else:
                settle_w = 0.0
            last_box_xform = _write_box_follow_frame(frame, settle_w)
        if frame >= f_b:
            break
        frame = min(frame + STEP, f_b)
    return last_box_xform

# 4) construir la secuencia completa
_write_pose_frame(rest_pose, F_START)
attr_box.Set(BOX_SHELF_XFORM, Usd.TimeCode(F_START))

_animate_segment(rest_pose, grab_pose, F_START, F_REACH)
_write_pose_frame(grab_pose, F_GRAB_HOLD)          # pausa: "cerrando el gripper"
attr_box.Set(BOX_SHELF_XFORM, Usd.TimeCode(F_GRAB_HOLD))

box_placed_xform = _animate_segment(grab_pose, place_pose, F_GRAB_HOLD, F_PLACE,
                                     box_follow=True, settle_start=F_PLACE - 20)

_write_pose_frame(place_pose, F_RELEASE)           # pausa: "soltando la caja"
attr_box.Set(m_settled, Usd.TimeCode(F_RELEASE))   # se mantiene asentada durante la pausa

_animate_segment(place_pose, rest_pose, F_RELEASE, F_RETURN)

# valores por defecto (para visores que no animan): brazo en reposo, caja ya colocada
attr_box.Set(m_settled, Usd.TimeCode.Default())

stage.SetStartTimeCode(F_START)
stage.SetEndTimeCode(F_RETURN)
stage.SetFramesPerSecond(FPS)
stage.SetTimeCodesPerSecond(FPS)

print(f"  animacion grabada: frames {F_START}-{F_RETURN} @ {FPS}fps "
      f"(alcanzar={F_REACH}, agarrar={F_GRAB_HOLD}, colocar={F_PLACE}, soltar={F_RELEASE}, reposo={F_RETURN})")

#Save to the end
stage.GetRootLayer().Save()
print(f"\nguardado: {OUT}")
print("\nprimeras lineas de lo que se escribio:")

for line in usda_text(stage).splitlines()[:12]:
    print(" |",line)


#B.)Add the path of the files usd
#1. building
#2. boxes
#3. materials

#C.)Adding the effects 
