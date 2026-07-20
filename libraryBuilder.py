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
