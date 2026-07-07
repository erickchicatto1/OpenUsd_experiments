from pxr import Usd, UsdGeom, UsdLux
import numpy as np

# Crear el Stage
stage = Usd.Stage.CreateNew("robot_scene.usda")

# Definir rango de tiempo para la animación
stage.SetStartTimeCode(0)
stage.SetEndTimeCode(6)   # último frame que definimos
stage.SetTimeCodesPerSecond(24)  # velocidad de reproducción (24 fps)

# Plano en el origen
plane = UsdGeom.Cube.Define(stage, "/Ground")
plane.AddScaleOp().Set((10, 10, 0.1))  # ancho y largo grandes, altura mínima

# Luz direccional tipo sol
sun = UsdLux.DistantLight.Define(stage, "/SunLight")
sun.CreateIntensityAttr(300)
sun.CreateColorAttr((1.0, 0.95, 0.9))  # tono cálido

# Crear un Xform contenedor para el robot
robot_xform = UsdGeom.Xform.Define(stage, "/RobotXform")

# Dentro del Xform, definir un Prim vacío que referencie tu robot
robot = stage.DefinePrim("/RobotXform/Robot")
robot.GetReferences().AddReference("D:/Robotics_AI/5.OpenUSD/mis_proyectos/sphere_robot.usdc")

# Rotar el Xform (no el Prim directamente)
xformOp = robot_xform.AddRotateXOp()
xformOp.Set(-90)

# Animar traslación en Z (vuelo: sube, flota, baja)
translateOp = robot_xform.AddTranslateOp()
translateOp.Set((0,0,0), time=0)   # inicio
translateOp.Set((0,0,4), time=2)   # sube
translateOp.Set((0,0,4), time=4)   # flota
translateOp.Set((0,0,0), time=6)   # baja

# Luz puntual adicional
light = UsdLux.SphereLight.Define(stage, "/SceneLight")
light.CreateIntensityAttr(500)

# Cámara
camera = UsdGeom.Camera.Define(stage, "/MainCamera")
camera.CreateFocusDistanceAttr(5.0)

# Guardar escena
stage.GetRootLayer().Save()
