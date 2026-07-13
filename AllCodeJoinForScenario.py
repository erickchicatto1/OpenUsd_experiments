#!/usr/bin/env python3
"""
building_gradual.py — plantilla para ir construyendo la nave por secciones
EN UN SOLO ARCHIVO, pudiendo LEER del stage entre paso y paso.

Reglas del juego:
  * El stage se crea UNA vez, arriba.
  * Cada seccion AUTORA sobre ese mismo stage en memoria.
  * Se GUARDA UNA vez, al final.
  * "Leer del stage" = consultar el objeto `stage` que ya tienes, no reabrir el .usda.
"""
import math
from pxr import Usd, UsdGeom, UsdShade, UsdLux, Sdf, Gf, Vt, Kind

OUT = "building.usda"


# =============================================================================
#  0) ABRIR O CREAR  — el patron idempotente
# =============================================================================
def open_or_create(path):
    """CreateNew() PETA si el archivo existe. Esto no.

    Tres alternativas segun lo que quieras:
      Usd.Stage.CreateNew(path)   -> falla si existe   (la que tenias)
      Usd.Stage.Open(path)        -> falla si NO existe
      Usd.Stage.CreateInMemory()  -> nunca toca disco  (ideal para experimentar)
    """
    if Usd.Stage.IsSupportedFile(path):
        layer = Sdf.Layer.FindOrOpen(path)          # ¿ya existe en disco?
        if layer:
            layer.Clear()                           # lo vaciamos y empezamos limpio
            return Usd.Stage.Open(layer)
    return Usd.Stage.CreateNew(path)


# =============================================================================
#  KIT DE LECTURA — las ~10 llamadas que necesitas para "leer del stage"
# =============================================================================
def dump(stage, title=""):
    """Arbol completo: path + tipo + apiSchemas aplicados."""
    print(f"\n--- ARBOL {title} " + "-" * 30)
    for prim in stage.Traverse():                   # recorre TODO el scenegraph
        apis = prim.GetAppliedSchemas()
        extra = f"  apis={list(apis)}" if apis else ""
        print(f"  {'  ' * (prim.GetPath().pathElementCount - 1)}"
              f"{prim.GetName():<16} [{prim.GetTypeName() or '-'}]{extra}")


def show(stage, path):
    """Ficha de UN prim: existe, tipo, atributos, transform y bbox."""
    prim = stage.GetPrimAtPath(path)                # <- LA llamada clave
    print(f"\n--- PRIM {path} " + "-" * 30)

    if not prim.IsValid():                          # ¡siempre comprobar!
        print("  NO EXISTE")
        return

    print(f"  tipo     : {prim.GetTypeName()}")
    print(f"  padre    : {prim.GetParent().GetPath()}")
    print(f"  hijos    : {[c.GetName() for c in prim.GetChildren()]}")
    print(f"  es Cube? : {prim.IsA(UsdGeom.Cube)}")

    # --- atributos: los que estan AUTORADOS (con valor escrito) ---
    print("  atributos autorados:")
    for attr in prim.GetAttributes():
        if attr.HasAuthoredValue():                 # filtra los defaults vacios
            print(f"    {attr.GetName():<22} = {attr.Get()}")

    # --- leer un atributo concreto: dos formas equivalentes ---
    if prim.IsA(UsdGeom.Cube):
        print(f"  size (generico) : {prim.GetAttribute('size').Get()}")
        print(f"  size (tipado)   : {UsdGeom.Cube(prim).GetSizeAttr().Get()}")

    # --- la transformacion: la lista de ops, en orden ---
    xf = UsdGeom.Xformable(prim)
    if xf:
        print("  xformOps:")
        for op in xf.GetOrderedXformOps():
            print(f"    {op.GetOpName():<22} = {op.Get()}")

        # matriz local (solo este prim) vs matriz a mundo (acumulando padres)
        local = xf.GetLocalTransformation()
        world = UsdGeom.XformCache().GetLocalToWorldTransform(prim)
        print(f"  traslacion local : {local.ExtractTranslation()}")
        print(f"  traslacion mundo : {world.ExtractTranslation()}")

    # --- bbox YA transformada a mundo: para comprobar donde acaba la cosa ---
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
    r = cache.ComputeWorldBound(prim).ComputeAlignedRange()
    if not r.IsEmpty():
        print(f"  bbox mundo : {[round(v, 2) for v in r.GetMin()]} -> "
              f"{[round(v, 2) for v in r.GetMax()]}")

    # --- material bindeado (si lo hay) ---
    mat = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()[0]
    if mat:
        print(f"  material : {mat.GetPath()}")


def find(stage, schema):
    """Todos los prims de un tipo. Ej: find(stage, UsdGeom.Cube)"""
    return [p for p in stage.Traverse() if p.IsA(schema)]


def usda_text(stage):
    """El .usda que se ESCRIBIRIA, sin tocar disco. Oro puro para depurar."""
    return stage.GetRootLayer().ExportToString()


# =============================================================================
#  A) EL EDIFICIO
# =============================================================================
LEN_X, HALF_Y = 60.0, 15.0
EAVE_Z, RIDGE_Z = 6.0, 9.0
WALL_T = 0.25

# ---------------------------------------------------------------- Paso 1: stage
stage = open_or_create(OUT)

# UsdGeom.Tokens.z NO es una letra: es un TfToken, un string "internado".
# USD usa tokens en vez de str por rendimiento (comparar dos tokens es comparar
# un puntero, no caracter a caracter) y para evitar erratas.
# UsdGeom.Tokens.z vale literalmente "Z". Podrias escribir "Z" a mano y funciona,
# pero el token te protege: si te equivocas, falla al importar, no en runtime.
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)      # == "Z"
UsdGeom.SetStageMetersPerUnit(stage, 1.0)

world = UsdGeom.Xform.Define(stage, "/World")
stage.SetDefaultPrim(world.GetPrim())
Usd.ModelAPI(world.GetPrim()).SetKind(Kind.Tokens.assembly)

print("PASO 1 — stage")
print("  upAxis      :", UsdGeom.GetStageUpAxis(stage))
print("  defaultPrim :", stage.GetDefaultPrim().GetPath())
dump(stage, "tras paso 1")


# ---------------------------------------------------------------- helper
def box(path, size, pos, rot=None):
    c = UsdGeom.Cube.Define(stage, path)
    c.CreateSizeAttr(2.0)
    c.CreateExtentAttr(Vt.Vec3fArray([Gf.Vec3f(-1, -1, -1), Gf.Vec3f(1, 1, 1)]))
    c.AddTranslateOp().Set(Gf.Vec3d(*pos))
    if rot:
        c.AddRotateXYZOp().Set(Gf.Vec3f(*rot))
    c.AddScaleOp().Set(Gf.Vec3f(size[0] / 2, size[1] / 2, size[2] / 2))
    return c


# ---------------------------------------------------------------- Paso 2: solera
UsdGeom.Xform.Define(stage, "/World/Building")
box("/World/Building/Floor", (LEN_X + 2, HALF_Y * 2 + 2, 0.30), (0, 0, -0.15))

print("\nPASO 2 — solera")
show(stage, "/World/Building/Floor")        # <-- AQUI LEES DEL STAGE

# leer para DECIDIR: ¿a que altura esta la cara superior de la solera?
cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
floor_top = cache.ComputeWorldBound(
    stage.GetPrimAtPath("/World/Building/Floor")).ComputeAlignedRange().GetMax()[2]
print(f"  -> la cota de apoyo para los muros es z = {floor_top}")


# ---------------------------------------------------------------- Paso 3: muros
box("/World/Building/Wall_Y_Neg", (LEN_X, WALL_T, EAVE_Z), (0, -HALF_Y, EAVE_Z / 2))
box("/World/Building/Wall_Y_Pos", (LEN_X, WALL_T, EAVE_Z), (0,  HALF_Y, EAVE_Z / 2))
box("/World/Building/Wall_X_Neg", (WALL_T, HALF_Y * 2, EAVE_Z), (-LEN_X / 2, 0, EAVE_Z / 2))
box("/World/Building/Wall_X_Pos", (WALL_T, HALF_Y * 2, EAVE_Z), ( LEN_X / 2, 0, EAVE_Z / 2))

print("\nPASO 3 — muros")
print("  cubos en el stage:", [p.GetName() for p in find(stage, UsdGeom.Cube)])
dump(stage, "tras paso 3")

# ...aqui seguirian pasos 4, 5, 6, 7 autorando sobre el MISMO `stage`...


# =============================================================================
#  GUARDAR — una sola vez, al final
# =============================================================================
stage.GetRootLayer().Save()
print(f"\nguardado: {OUT}")
print("\nprimeras lineas de lo que se escribio:")
for line in usda_text(stage).splitlines()[:12]:
    print("  |", line)
