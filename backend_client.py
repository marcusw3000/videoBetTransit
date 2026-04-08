from __future__ import annotations

import importlib.util
import pathlib
import sys
from types import ModuleType

_REPO_ROOT = pathlib.Path(__file__).resolve().parent
_WORKER_DIR = _REPO_ROOT / "vision-worker"
_WORKER_MODULE_PATH = _WORKER_DIR / "backend_client.py"


def _load_worker_module() -> ModuleType:
    if not _WORKER_MODULE_PATH.exists():
        raise FileNotFoundError(f"Modulo oficial nao encontrado em {_WORKER_MODULE_PATH}")

    worker_path = str(_WORKER_DIR)
    if worker_path not in sys.path:
        sys.path.insert(0, worker_path)

    spec = importlib.util.spec_from_file_location("vision_worker_backend_client", _WORKER_MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Nao foi possivel carregar {_WORKER_MODULE_PATH}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_WORKER_MODULE = _load_worker_module()

for _name, _value in vars(_WORKER_MODULE).items():
    if _name in {"__name__", "__file__", "__package__", "__loader__", "__spec__"}:
        continue
    globals()[_name] = _value

__doc__ = getattr(_WORKER_MODULE, "__doc__", None)
__all__ = getattr(
    _WORKER_MODULE,
    "__all__",
    [name for name in globals() if not name.startswith("_")],
)
