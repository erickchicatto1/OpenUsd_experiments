"""
learn_all_arcs.py (v2 - con matematicas Gf y logica de validacion)
====================================================================
Ademas de los 6 arcos de composicion (Local, Inherits, VariantSets,
References, Payload, Specializes), esta version agrega:

  - pxr.Gf para el layout espacial del block: Gf.Vec3d (posiciones),
    Gf.Rotation + Gf.Matrix4d (rotacion+traslacion combinadas en un solo
    xformOp:transform), y Gf.Range3d (bounding box del block completo).

  - Logica de validacion (LayoutValidator) que opera sobre los VALORES
    YA RESUELTOS por la composicion: chequeo de separacion minima entre
    lotes (matematica Gf: distancia entre Gf.Vec3d) y chequeo de
    cumplimiento normativo (altura solicitada vs code:maxHeightMeters,
    que cambia segun el escenario gracias a specializes/inherits).
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from pxr import Usd, UsdGeom, Sdf, Gf


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class BuildingCodeConfig:
    max_height_meters: int = 30
    fire_rating: str = "A"


@dataclass
class TrafficZoneConfig:
    maxspeed: int = 30
    noiselimit: int = 55


@dataclass
class ZoningConfig:
    allowed_use: str = "residential"
    max_floors: int = 4


@dataclass
class VariantStyle:
    name: str
    roof_type: str
    facade_color: Tuple[float, float, float]


@dataclass
class LotPlacement:
    """Todo lo que hace falta para colocar UN lote dentro del block:
    a que archivo referencia, que variante usa, donde se ubica (Gf.Vec3d),
    cuanto rota (grados sobre Y) y que altura de edificio se propone
    (para la validacion normativa)."""
    name: str
    lot_file: str
    variant: str
    position: Gf.Vec3d
    rotation_degrees: float
    requested_height_meters: float


# ---------------------------------------------------------------------------
# PASO 0 - Piezas base de la libreria
# ---------------------------------------------------------------------------

class LibraryBuilder:
    def __init__(self, working_dir: Path):
        self.working_dir = working_dir

    def build_shell(self) -> Path:
        path = self.working_dir / "building_shell.usd"
        stage = Usd.Stage.CreateNew(str(path))
        stage.SetDefaultPrim(stage.DefinePrim("/Shell", "Xform"))
        stage.DefinePrim("/Shell/Facade", "Mesh")
        stage.GetRootLayer().Save()
        print(f"[LibraryBuilder] creado: {path.name}")
        return path

    def build_interior(self, furniture_count: int = 3) -> Path:
        path = self.working_dir / "building_interior.usd"
        stage = Usd.Stage.CreateNew(str(path))
        stage.SetDefaultPrim(stage.DefinePrim("/Interior", "Xform"))
        for i in range(furniture_count):
            stage.DefinePrim(f"/Interior/Furniture_{i}", "Mesh")
        stage.GetRootLayer().Save()
        print(f"[LibraryBuilder] creado: {path.name}")
        return path

    def build_all(self):
        self.build_shell()
        self.build_interior()


# ---------------------------------------------------------------------------
# PASO 1 - building_asset.usd
# ---------------------------------------------------------------------------

class BuildingAssetBuilder:
    FILENAME = "building_asset.usd"

    def __init__(self, working_dir: Path, code: BuildingCodeConfig,
                 traffic: TrafficZoneConfig, variants: List[VariantStyle],
                 default_variant: str):
        self.working_dir = working_dir
        self.code = code
        self.traffic = traffic
        self.variants = variants
        self.default_variant = default_variant

    def build(self) -> Path:
        path = self.working_dir / self.FILENAME
        stage = Usd.Stage.CreateNew(str(path))
        building = stage.DefinePrim("/Building", "Xform")
        stage.SetDefaultPrim(building)

        self._add_reference_shell(stage)
        self._add_payload_interior(stage)
        self._add_variant_styles(building)
        self._add_inherits_building_code(stage, building)
        self._add_specializes_traffic_zone(stage, building)

        stage.GetRootLayer().Save()
        print(f"[BuildingAssetBuilder] creado: {path.name}")
        return path

    def _add_reference_shell(self, stage: Usd.Stage):
        shell_ref = stage.DefinePrim("/Building/Shell", "Xform")
        shell_ref.GetReferences().AddReference("./building_shell.usd")

    def _add_payload_interior(self, stage: Usd.Stage):
        interior_pl = stage.DefinePrim("/Building/Interior", "Xform")
        interior_pl.GetPayloads().AddPayload("./building_interior.usd")

    def _add_variant_styles(self, building: Usd.Prim):
        vset = building.GetVariantSets().AddVariantSet("style")
        for variant in self.variants:
            vset.AddVariant(variant.name)

        for variant in self.variants:
            vset.SetVariantSelection(variant.name)
            with vset.GetVariantEditContext():
                building.CreateAttribute(
                    "style:roofType", Sdf.ValueTypeNames.Token, custom=True
                ).Set(variant.roof_type)
                building.CreateAttribute(
                    "style:facadeColor", Sdf.ValueTypeNames.Color3f, custom=True
                ).Set(variant.facade_color)

        vset.SetVariantSelection(self.default_variant)

    def _add_inherits_building_code(self, stage: Usd.Stage, building: Usd.Prim):
        code_class = stage.CreateClassPrim("/_building_code")
        code_class.CreateAttribute(
            "code:maxHeightMeters", Sdf.ValueTypeNames.Int, custom=True
        ).Set(self.code.max_height_meters)
        code_class.CreateAttribute(
            "code:fireRating", Sdf.ValueTypeNames.Token, custom=True
        ).Set(self.code.fire_rating)
        building.GetInherits().AddInherit(code_class.GetPath())

    def _add_specializes_traffic_zone(self, stage: Usd.Stage, building: Usd.Prim):
        traffic_class = stage.CreateClassPrim("/_traffic_zone_data")
        traffic_class.CreateAttribute(
            "osm:zone:maxspeed", Sdf.ValueTypeNames.Int, custom=True
        ).Set(self.traffic.maxspeed)
        traffic_class.CreateAttribute(
            "osm:zone:noiselimit", Sdf.ValueTypeNames.Int, custom=True
        ).Set(self.traffic.noiselimit)
        building.GetSpecializes().AddSpecialize(traffic_class.GetPath())


# ---------------------------------------------------------------------------
# PASO 2 - Lotes
# ---------------------------------------------------------------------------

class LotBuilder:
    def __init__(self, working_dir: Path):
        self.working_dir = working_dir

    def build_lot(self, placement: LotPlacement) -> Path:
        path = self.working_dir / placement.lot_file
        stage = Usd.Stage.CreateNew(str(path))
        lot = stage.DefinePrim("/Lot", "Xform")
        stage.SetDefaultPrim(lot)
        building = stage.DefinePrim("/Lot/Building", "Xform")
        building.GetReferences().AddReference("./building_asset.usd")
        building.GetVariantSet("style").SetVariantSelection(placement.variant)

        # Opinion LOCAL simple (no es un arco de composicion, es solo un
        # dato de diseno) usada mas adelante por LayoutValidator.
        building.CreateAttribute(
            "building:requestedHeightMeters", Sdf.ValueTypeNames.Float, custom=True
        ).Set(placement.requested_height_meters)

        stage.GetRootLayer().Save()
        print(f"[LotBuilder] creado: {placement.lot_file} (variante={placement.variant})")
        return path


# ---------------------------------------------------------------------------
# PASO 3 - block.usd: SUBLAYERS + REFERENCES + layout espacial con Gf
# ---------------------------------------------------------------------------

class BlockBuilder:
    def __init__(self, working_dir: Path, zoning_base: ZoningConfig,
                 downtown_allowed_use: str, placements: List[LotPlacement]):
        self.working_dir = working_dir
        self.zoning_base = zoning_base
        self.downtown_allowed_use = downtown_allowed_use
        self.placements = placements

    def build(self) -> Path:
        self._build_zoning_base()
        self._build_zoning_downtown_overrides()
        return self._build_block()

    def _build_zoning_base(self):
        path = self.working_dir / "zoning_base.usd"
        stage = Usd.Stage.CreateNew(str(path))
        zi = stage.DefinePrim("/ZoningInfo", "Scope")
        zi.CreateAttribute(
            "zone:allowedUse", Sdf.ValueTypeNames.Token, custom=True
        ).Set(self.zoning_base.allowed_use)
        zi.CreateAttribute(
            "zone:maxFloors", Sdf.ValueTypeNames.Int, custom=True
        ).Set(self.zoning_base.max_floors)
        stage.GetRootLayer().Save()
        print(f"[BlockBuilder] creado: {path.name}")

    def _build_zoning_downtown_overrides(self):
        path = self.working_dir / "zoning_downtown_overrides.usd"
        stage = Usd.Stage.CreateNew(str(path))
        zi = stage.OverridePrim("/ZoningInfo")
        zi.CreateAttribute(
            "zone:allowedUse", Sdf.ValueTypeNames.Token, custom=True
        ).Set(self.downtown_allowed_use)
        stage.GetRootLayer().Save()
        print(f"[BlockBuilder] creado: {path.name}")

    def _build_block(self) -> Path:
        path = self.working_dir / "block.usd"
        stage = Usd.Stage.CreateNew(str(path))
        stage.GetRootLayer().subLayerPaths.append("./zoning_downtown_overrides.usd")
        stage.GetRootLayer().subLayerPaths.append("./zoning_base.usd")

        block = stage.DefinePrim("/Block", "Xform")
        stage.SetDefaultPrim(block)

        for placement in self.placements:
            prim = stage.DefinePrim(f"/Block/{placement.name}", "Xform")
            prim.GetReferences().AddReference(f"./{placement.lot_file}")
            self._author_transform(prim, placement)

        stage.GetRootLayer().Save()
        print(f"[BlockBuilder] creado: {path.name}")
        return path

    @staticmethod
    def _author_transform(prim: Usd.Prim, placement: LotPlacement):
        """Matematica de Gf: combina rotacion (Gf.Rotation) y traslacion
        (Gf.Vec3d) en una sola matriz 4x4 (Gf.Matrix4d) y la autoriza como
        un unico xformOp:transform."""
        rotation = Gf.Rotation(Gf.Vec3d(0, 1, 0), placement.rotation_degrees)
        rotation_matrix = Gf.Matrix4d(1.0).SetRotate(rotation)
        translation_matrix = Gf.Matrix4d(1.0).SetTranslate(placement.position)
        transform = rotation_matrix * translation_matrix  # rota y LUEGO traslada

        xformable = UsdGeom.Xformable(prim)
        xformable.ClearXformOpOrder()
        xformable.AddTransformOp().Set(transform)

    @staticmethod
    def compute_block_extent(placements: List[LotPlacement], footprint_radius: float) -> Gf.Range3d:
        """Otra operacion de Gf: Gf.Range3d acumula un bounding box a partir
        de las posiciones de todos los lotes + su radio de huella."""
        extent = Gf.Range3d()
        for placement in placements:
            corner_min = placement.position - Gf.Vec3d(footprint_radius, 0, footprint_radius)
            corner_max = placement.position + Gf.Vec3d(footprint_radius, 0, footprint_radius)
            extent.UnionWith(corner_min)
            extent.UnionWith(corner_max)
        return extent


# ---------------------------------------------------------------------------
# PASO 4 - Escenarios finales
# ---------------------------------------------------------------------------

class ScenarioBuilder:
    def __init__(self, working_dir: Path):
        self.working_dir = working_dir

    def build_scenario(self, filename: str,
                        override_traffic: Optional[TrafficZoneConfig] = None,
                        override_code: Optional[BuildingCodeConfig] = None) -> Path:
        path = self.working_dir / filename
        stage = Usd.Stage.CreateNew(str(path))
        city = stage.DefinePrim("/City", "Xform")
        stage.SetDefaultPrim(city)
        blk = stage.DefinePrim("/City/Block", "Xform")
        blk.GetReferences().AddReference("./block.usd")

        if override_traffic is not None:
            traffic_class = stage.CreateClassPrim("/_traffic_zone_data")
            traffic_class.CreateAttribute(
                "osm:zone:maxspeed", Sdf.ValueTypeNames.Int, custom=True
            ).Set(override_traffic.maxspeed)
            traffic_class.CreateAttribute(
                "osm:zone:noiselimit", Sdf.ValueTypeNames.Int, custom=True
            ).Set(override_traffic.noiselimit)

        if override_code is not None:
            code_class = stage.CreateClassPrim("/_building_code")
            code_class.CreateAttribute(
                "code:maxHeightMeters", Sdf.ValueTypeNames.Int, custom=True
            ).Set(override_code.max_height_meters)

        stage.GetRootLayer().Save()
        overridden = "si" if (override_traffic or override_code) else "no"
        print(f"[ScenarioBuilder] creado: {filename} (override={overridden})")
        return path


# ---------------------------------------------------------------------------
# PASO 5 - Inspeccion + LOGICA de validacion sobre valores ya resueltos
# ---------------------------------------------------------------------------

class CompositionInspector:
    def __init__(self, working_dir: Path):
        self.working_dir = working_dir

    def report_scenario(self, scenario_file: str, lots: List[Tuple[str, str]]):
        print(f"\n{'='*70}\n{scenario_file}\n{'='*70}")
        stage = Usd.Stage.Open(str(self.working_dir / scenario_file))
        for lot_name, expected_style in lots:
            b = stage.GetPrimAtPath(f"/City/Block/{lot_name}/Building")
            print(f"\n{lot_name} (variante esperada: {expected_style})")
            print("  style:roofType       =", b.GetAttribute("style:roofType").Get(), " (variantSet)")
            print("  code:maxHeightMeters =", b.GetAttribute("code:maxHeightMeters").Get(), " (inherits)")
            print("  osm:zone:maxspeed    =", b.GetAttribute("osm:zone:maxspeed").Get(), " (specializes)")
            interior = stage.GetPrimAtPath(f"/City/Block/{lot_name}/Building/Interior")
            print("  Interior cargado (payload)?", interior.IsLoaded())

    def report_sublayers(self):
        print(f"\n{'='*70}\nblock.usd (efecto de subLayers)\n{'='*70}")
        stage = Usd.Stage.Open(str(self.working_dir / "block.usd"))
        zoning = stage.GetPrimAtPath("/ZoningInfo")
        print("zone:allowedUse =", zoning.GetAttribute("zone:allowedUse").Get(),
              "(gana downtown, listada primero)")
        print("zone:maxFloors  =", zoning.GetAttribute("zone:maxFloors").Get(),
              "(downtown no lo toca -> cae a zoning_base)")

    def report_layout(self, placements: List[LotPlacement], footprint_radius: float):
        print(f"\n{'='*70}\nLayout espacial (Gf.Vec3d / Gf.Matrix4d / Gf.Range3d)\n{'='*70}")
        stage = Usd.Stage.Open(str(self.working_dir / "block.usd"))
        cache = UsdGeom.XformCache()
        for placement in placements:
            prim = stage.GetPrimAtPath(f"/Block/{placement.name}")
            world_matrix = cache.GetLocalToWorldTransform(prim)
            world_pos = world_matrix.Transform(Gf.Vec3d(0, 0, 0))
            print(f"  {placement.name}: posicion mundial = {world_pos}")

        extent = BlockBuilder.compute_block_extent(placements, footprint_radius)
        print(f"  Extent total del block (Gf.Range3d) = min{extent.GetMin()} max{extent.GetMax()}")

    def demo_payload_loading(self, scenario_file: str):
        print(f"\n{'='*70}\nCarga diferida de payloads ({scenario_file})\n{'='*70}")
        stage = Usd.Stage.Open(str(self.working_dir / scenario_file), load=Usd.Stage.LoadNone)
        int1 = stage.GetPrimAtPath("/City/Block/Lot01/Building/Interior")
        int2 = stage.GetPrimAtPath("/City/Block/Lot02/Building/Interior")
        print("Antes de Load():", int1.IsLoaded())
        stage.Load(int1.GetPath())
        print("Despues de Load() solo en Lot01:", int1.IsLoaded())
        print("Lot02 sigue sin cargar:", int2.IsLoaded())


class LayoutValidator:
    """Logica de validacion pura de Python/Gf que opera sobre los valores
    YA RESUELTOS por la composicion (no autoriza nada nuevo en USD)."""

    def __init__(self, working_dir: Path):
        self.working_dir = working_dir

    def check_clearance(self, placements: List[LotPlacement], min_clearance: float):
        print(f"\n--- Validacion de separacion minima (>= {min_clearance} m) ---")
        for i in range(len(placements)):
            for j in range(i + 1, len(placements)):
                a, b = placements[i], placements[j]
                distance = (b.position - a.position).GetLength()  # matematica Gf
                status = "OK" if distance >= min_clearance else "MUY CERCA"
                print(f"  {a.name} <-> {b.name}: distancia = {distance:.1f} m -> {status}")

    def check_building_code(self, scenario_file: str, placements: List[LotPlacement]):
        print(f"\n--- Cumplimiento normativo en {scenario_file} ---")
        stage = Usd.Stage.Open(str(self.working_dir / scenario_file))
        for placement in placements:
            b = stage.GetPrimAtPath(f"/City/Block/{placement.name}/Building")
            allowed = b.GetAttribute("code:maxHeightMeters").Get()  # viene de INHERITS
            requested = b.GetAttribute("building:requestedHeightMeters").Get()  # local
            compliant = requested <= allowed
            veredicto = "CUMPLE" if compliant else "EXCEDE EL LIMITE"
            print(f"  {placement.name}: solicitado={requested}m, permitido={allowed}m -> {veredicto}")


# ---------------------------------------------------------------------------
# Orquestacion
# ---------------------------------------------------------------------------

def main():
    working_dir = Path(__file__).parent
    FOOTPRINT_RADIUS = 10.0   # "radio" aproximado de cada edificio, en metros
    MIN_CLEARANCE = 30.0      # separacion minima exigida entre lotes

    print("### PASO 0: libreria ###")
    LibraryBuilder(working_dir).build_all()

    print("\n### PASO 1: building_asset.usd ###")
    code_cfg = BuildingCodeConfig()
    traffic_cfg = TrafficZoneConfig()
    variants = [
        VariantStyle("modern", "flat", (0.6, 0.6, 0.65)),
        VariantStyle("classic", "peaked", (0.8, 0.5, 0.3)),
    ]
    BuildingAssetBuilder(working_dir, code_cfg, traffic_cfg, variants,
                         default_variant="modern").build()

    print("\n### PASO 2: lotes (layout con Gf.Vec3d / Gf.Rotation) ###")
    placements = [
        LotPlacement("Lot01", "lot_01.usd", "modern",
                     position=Gf.Vec3d(0, 0, 0), rotation_degrees=0,
                     requested_height_meters=25.0),
        LotPlacement("Lot02", "lot_02.usd", "classic",
                     position=Gf.Vec3d(50, 0, 0), rotation_degrees=180,
                     requested_height_meters=45.0),
    ]
    lot_builder = LotBuilder(working_dir)
    for placement in placements:
        lot_builder.build_lot(placement)

    print("\n### PASO 3: block.usd (sublayers + references + transforms Gf) ###")
    zoning_cfg = ZoningConfig()
    BlockBuilder(working_dir, zoning_cfg, downtown_allowed_use="commercial",
                 placements=placements).build()

    print("\n### PASO 4: escenarios ###")
    scenario_builder = ScenarioBuilder(working_dir)
    scenario_builder.build_scenario("city_scenario_normal.usd")
    scenario_builder.build_scenario(
        "city_scenario_special_event.usd",
        override_traffic=TrafficZoneConfig(maxspeed=10, noiselimit=40),
        override_code=BuildingCodeConfig(max_height_meters=50),
    )

    print("\n### PASO 5: inspeccion ###")
    inspector = CompositionInspector(working_dir)
    lots_summary = [(p.name, p.variant) for p in placements]
    inspector.report_scenario("city_scenario_normal.usd", lots_summary)
    inspector.report_scenario("city_scenario_special_event.usd", lots_summary)
    inspector.report_sublayers()
    inspector.report_layout(placements, FOOTPRINT_RADIUS)
    inspector.demo_payload_loading("city_scenario_normal.usd")

    print("\n### PASO 6: logica de validacion (Gf + reglas de negocio) ###")
    validator = LayoutValidator(working_dir)
    validator.check_clearance(placements, MIN_CLEARANCE)
    validator.check_building_code("city_scenario_normal.usd", placements)
    validator.check_building_code("city_scenario_special_event.usd", placements)


if __name__ == "__main__":
    main()
