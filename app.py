from __future__ import annotations

import importlib.util
import pathlib
import sys
from types import ModuleType

_REPO_ROOT = pathlib.Path(__file__).resolve().parent
_WORKER_DIR = _REPO_ROOT / "vision-worker"
_WORKER_APP = _WORKER_DIR / "app.py"


def _load_worker_module() -> ModuleType:
    if not _WORKER_APP.exists():
        raise FileNotFoundError(f"Worker oficial nao encontrado em {_WORKER_APP}")

    worker_path = str(_WORKER_DIR)
    if worker_path not in sys.path:
        sys.path.insert(0, worker_path)

    spec = importlib.util.spec_from_file_location("vision_worker_app", _WORKER_APP)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Nao foi possivel carregar {_WORKER_APP}")

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


if __name__ == "__main__":
    print("[compat] app.py da raiz foi aposentado; redirecionando para vision-worker\\app.py")
    sys.exit(main())
