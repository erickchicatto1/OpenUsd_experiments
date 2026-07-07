from pxr import Usd, UsdGeom, UsdLux

stage = Usd.Stage.CreateNew("robot_scene.usda")

# Crear un Xform contenedor
robot_xform = UsdGeom.Xform.Define(stage, "/RobotXform")

# Dentro del Xform, definir un Prim vacío que referencie tu robot
robot = stage.DefinePrim("/RobotXform/Robot")
robot.GetReferences().AddReference("D:/Robotics_AI/5.OpenUSD/mis_proyectos/sphere_robot.usdc")

# Rotar el Xform (no el Prim directamente)
xformOp = robot_xform.AddRotateXOp()
xformOp.Set(-90)

# Agregar una luz
light = UsdLux.SphereLight.Define(stage, "/SceneLight")
light.CreateIntensityAttr(500)

# Agregar una cámara
camera = UsdGeom.Camera.Define(stage, "/MainCamera")
camera.CreateFocusDistanceAttr(5.0)

stage.GetRootLayer().Save()
