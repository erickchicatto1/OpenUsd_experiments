import os
from pathlib import Path

from pxr import Usd, UsdGeom, Sdf


working_dir = Path(__file__).parent
side_streets = ["road_straight_59", "road_straight_34", "road_straight_28", "road_straight_27"]

asset_stage = Usd.Stage.Open(str(working_dir / "main_street.usd"))
class_prim = asset_stage.CreateClassPrim("/_osm_street_data")
max_speed_attr = class_prim.CreateAttribute("osm:street:maxspeed", Sdf.ValueTypeNames.Int, custom=True)
max_speed_attr.Set(30)
for prim in asset_stage.Traverse():
    if prim.IsA(UsdGeom.Mesh) and prim.GetName().startswith("road_") and not "Barrier" in prim.GetName():
        prim.GetSpecializes().AddSpecialize(class_prim.GetPath())
        if prim.GetName() in side_streets:
            prim.GetAttribute("osm:street:maxspeed").Set(20)


asset_stage.Save()


scenario2 = Usd.Stage.Open(str(working_dir / "scenario_02.usd"))
class_prim = scenario2.OverridePrim("/_osm_street_data")
max_speed_attr = class_prim.CreateAttribute("osm:street:maxspeed", Sdf.ValueTypeNames.Int, custom=True)
max_speed_attr.Set(40)
scenario2.Save()
