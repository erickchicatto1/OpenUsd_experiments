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
gap = 2.0  # metros de pasillo entre el rack y el robot
target_x_amr = target_x_rack + rack_half_x + gap
target_y_amr = target_y_rack

dx = target_x_amr - center_x1
dy = target_y_amr - center_y1
dz = floor_top - bmin1[2]

# 4) aplicar la transformacion final completa de una sola vez
set_full_xform(amr, factor_escala, 90, (dx, dy, dz))

print("\nPASO 6 — AMR/cobot")
show(stage, "/World/Building/AMR_Cobot")

#Step 7 , add maths to the cobot in a new file

#Step 8 , make the animation 

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
