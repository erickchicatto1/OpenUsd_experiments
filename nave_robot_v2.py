from pxr import Usd, UsdGeom, UsdLux, UsdShade, Sdf
import math
import numpy as np 

#Functions 
def crear_material(nombre,color_rgb):
    mat = UsdShade.Material.Define(stage,f"/Materials/{nombre}")
    shader = UsdShade.Shader.Define(stage,f"/Materials/{nombre}/Shader")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(color_rgb)
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.3) # Ligeramente brillante
    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return mat

def bind_pieza(parent_path,material):
    parent_prim = stage.GetPrimAtPath(parent_path)
    
    if not parent_prim:
        return False
    
    nombre_pieza = parent_path.rstrip("/").split("/")[-1]
    mesh_path = f"{parent_path}/{nombre_pieza}"
    mesh_prim = stage.GetPrimAtPath(mesh_path)
    objetivo = mesh_prim if mesh_prim.isValid() else parent_prim
    UsdShade.MaterialBindingAPI.Apply(objetivo).Bind(material)
    return True

    
#crear el stage
stage = Usd.Stage.CreateNew("robot_scene.usda")

#tiempo 
stage.SetStartTimeCode(0)
stage.SetEndTimeCode(144)
stage.SetTimeCodesPerSecond(24)

#Luces
dome_light = UsdLux.DomeLight.Define(stage, "/SkyDome")
dome_light.CreateIntensityAttr(1.5)  # Intensidad realista para domos en USD
dome_light.CreateColorAttr((0.2, 0.5, 0.9))  # Fondo azul cielo

sun = UsdLux.DistantLight.Define(stage, "/SunLight")
sun.CreateIntensityAttr(2.0)  # Intensidad moderada para el sol
sun.CreateColorAttr((1.0, 0.95, 0.9))

#referencias del robot
robot_xform = UsdGeom.Xform.Define(stage, "/RobotXform")
robot = stage.DefinePrim("/RobotXform/Robot")
robot.GetReferences().AddReference("D:/Robotics_AI/5.OpenUSD/mis_proyectos/BasicBot.usdc")

#rotacion 
xformOp = robot_xform.AddRotateXOp()
xformOp.Set(-90)

#Asignamos el material 
material_rojo = crear_material("MaterialRojo", (0.8, 0.02, 0.02))
material_azul = crear_material("MaterialAzul", (0.02, 0.15, 0.8))

#ecuacion parametrica del circulo 
translateOp = robot_xform.AddTranslateOp()
rotateZOp = robot_xform.AddRotateZOp()

radio = 4.0
altura_base = 3.0
amplitud_vertical = 0.3
vueltas = 2

frame_inicial = int(stage.GetStartTimeCode())
frame_final = int(stage.GetEndTimeCode())

for frame in range(frame_inicial,frame_final + 1 ,2): # cada 2 frames
    progreso = (frame-frame_inicial)/(frame_final - frame_inicial)
    angulo = progreso*vueltas * 2 *math.pi
    
    #ecuacion parametrica del circulo 
    x = radio * math.cos(angulo)
    y = radio * math.sin(angulo)
    #ecuacion aparte
    z = altura_base + amplitud_vertical * math.sin(angulo*3)
    translateOp.Set((x,y,z),time=frame)
    
    #angulo tangente a la trayectoria (derivada de la posicion circular)
    angulo_tangente = math.degrees(angulo)+90
    rotateZOp.Set(angulo_tangente, time=frame)
    
# Luz de relleno reducida para que no queme la escena
light = UsdLux.SphereLight.Define(stage, "/SceneLight")
light.CreateIntensityAttr(5.0)
light.AddTranslateOp().Set((0, 0, 6)) # La subimos para que ilumine desde arriba

material_nube = crear_material("MaterialNube", (0.95, 0.95, 0.97))

# El prototipo vive bajo su propio scope y se marca como invisible:
# el PointInstancer es quien se encarga de dibujar las copias visibles.
cloud_proto = UsdGeom.Sphere.Define(stage, "/Clouds/Prototypes/Cloud")
cloud_proto.CreateRadiusAttr(1.4)
UsdShade.MaterialBindingAPI.Apply(cloud_proto.GetPrim()).Bind(material_nube)
UsdGeom.Imageable(cloud_proto).CreateVisibilityAttr("invisible")
    
instancer = UsdGeom.PointInstancer.Define(stage, "/Clouds/Instancer")
instancer.CreatePrototypesRel().SetTargets([cloud_proto.GetPath()])

# Posiciones dispersas en el cielo, arriba y alrededor del robot (x, y, z)
posiciones_nubes = [
    (4, 3, 5), (-3, 2, 5.5), (2, -4, 4.7), (-5, -2, 5.2),
    (6, 0, 4.5), (-2, 4, 5.8), (0, 0, 6), (3, -1, 5.1),
]
# Escalamos cada nube distinto en X/Y/Z para que no sean esferas perfectas
escalas_nubes = [
    (2.2, 1.3, 0.8), (1.8, 1.1, 0.7), (2.5, 1.4, 0.9), (2.0, 1.2, 0.75),
    (1.6, 1.0, 0.65), (2.3, 1.3, 0.85), (1.9, 1.1, 0.7), (2.1, 1.2, 0.8),
]

instancer.CreatePositionsAttr(posiciones_nubes)
instancer.CreateScalesAttr(escalas_nubes)
instancer.CreateProtoIndicesAttr([0] * len(posiciones_nubes))


#camara
camera = UsdGeom.Camera.Define(stage, "/MainCamera")
camera.CreateFocusDistanceAttr(6.0)
camera.AddTranslateOp().Set((0, -12, 4))
camera.AddRotateXOp().Set(80)

# Guardar escena
stage.GetRootLayer().Save()
print("¡Escena actualizada! Vuelve a abrir usdview.")
