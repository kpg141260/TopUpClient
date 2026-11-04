__VERSION__ = "0.5.0.2"
# ruff: noqa: RUF100, UP025, UP004, I001, F401
# <VT_VERSION_OBJECT_START>
import json
import os

__VT_FILE__ = "res/vt_version_object.py"
__VT_MANIFEST__ = "version_manifest.json"

class VersionInfo:
    def __init__(self, manifest_name=__VT_MANIFEST__, file_name=__VT_FILE__):
        self.manifest_name = manifest_name
        self.file_name = file_name
        self.data = self._load()

    def _load(self):
        folder = os.path.dirname(__file__) if "__file__" in globals() else "."
        while True:
            path = os.path.join(folder, self.manifest_name)
            if os.path.isfile(path):
                with open(path, "r") as f:
                    return json.load(f)

            parent = os.path.dirname(folder)
            if parent == folder:
                return {}
            folder = parent

    @property
    def project(self) -> dict:
        return self.data.get("project", {})

    @property
    def build_info(self) -> dict:
        return self.project.get("build_info", {})

    @property
    def file(self) -> dict:
        return self.data.get(self.file_name, {})

    @property
    def all(self) -> dict:
        data = {}
        b = self.build_info
        for key, item in self.data.items():
            if key == 'project':
                data.setdefault("Overall Project Version:", f"{b.get('major', 0)}.{b.get('minor', 0)}.{b.get('patch', 0)}.{b.get('build', 0)}")
            else:
                data.setdefault(key, f"{b.get('major', 0)}.{b.get('minor', 0)}.{b.get('patch', 0)}.{item.get('build', 0)}")
        sorted_d = dict(sorted(data.items()))
        return sorted_d

    @property
    def version(self) -> str:
        b = self.build_info
        build = self.file.get("build", b.get("build", 0))
        return f"{b.get('major', 0)}.{b.get('minor', 0)}.{b.get('patch', 0)}.{build}"

__version_info__ = VersionInfo()
__VERSION__ = __version_info__.version
# <VT_VERSION_OBJECT_END>

