"""A PEP 517/660 build backend installing this tree's makepanda build in place.

Panda3D is built by makepanda, not by a Python build backend, so pip and uv
cannot build it from this tree. This backend lets them install the build
that makepanda has already made, editably: ``uv add --editable <this tree>``
or ``pip install -e <this tree>``.

The "wheel" it makes holds the ``panda3d`` distribution's metadata (its name
and version from setup.cfg) and a ``.pth`` file putting this tree's
``built`` directory on ``sys.path``. The packages there (``panda3d``,
``direct``, ``pandac``) are then imported straight from the build, and
``panda3d/__init__.py`` adds ``built/bin`` for the DLLs. Run makepanda again
and the environment sees the new build at once, with nothing reinstalled.

There is nothing to build here, so a plain (not editable) wheel is the same
thing: it too only points at ``built``. For a real, self-contained wheel use
makepanda's ``--wheel``.
"""

import base64
import configparser
import hashlib
import io
import os
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILT = os.path.join(ROOT, "built")
TAG = "py3-none-any"


def _metadata():
    config = configparser.ConfigParser()
    config.read(os.path.join(ROOT, "setup.cfg"), encoding="utf-8")
    meta = config["metadata"]
    return meta["name"], meta["version"], meta.get("description", "")


def _dist_info():
    name, version, _ = _metadata()
    return f"{name}-{version}.dist-info"


def _metadata_text():
    name, version, description = _metadata()
    return (
        "Metadata-Version: 2.1\n"
        f"Name: {name}\n"
        f"Version: {version}\n"
        f"Summary: {description} (this tree's makepanda build, in place)\n"
    )


def _wheel_text():
    return (
        "Wheel-Version: 1.0\n"
        "Generator: panda3d makepanda/editable_backend.py\n"
        "Root-Is-Purelib: true\n"
        f"Tag: {TAG}\n"
    )


def _record_line(path, data):
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=")
    return f"{path},sha256={digest.decode()},{len(data)}"


def _build(wheel_directory):
    if not os.path.isdir(os.path.join(BUILT, "panda3d")):
        msg = f"no makepanda build in {BUILT}: run makepanda first"
        raise RuntimeError(msg)
    name, version, _ = _metadata()
    dist_info = _dist_info()
    files = {
        f"_{name}_built.pth": (BUILT + "\n").encode("utf-8"),
        f"{dist_info}/METADATA": _metadata_text().encode("utf-8"),
        f"{dist_info}/WHEEL": _wheel_text().encode("utf-8"),
    }
    record = [_record_line(path, data) for path, data in files.items()]
    record.append(f"{dist_info}/RECORD,,")
    files[f"{dist_info}/RECORD"] = ("\n".join(record) + "\n").encode("utf-8")
    filename = f"{name}-{version}-{TAG}.whl"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as wheel:
        for path, data in files.items():
            wheel.writestr(path, data)
    with open(os.path.join(wheel_directory, filename), "wb") as out:
        out.write(buffer.getvalue())
    return filename


def _prepare_metadata(metadata_directory):
    dist_info = _dist_info()
    folder = os.path.join(metadata_directory, dist_info)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "METADATA"), "w", encoding="utf-8") as out:
        out.write(_metadata_text())
    with open(os.path.join(folder, "WHEEL"), "w", encoding="utf-8") as out:
        out.write(_wheel_text())
    return dist_info


def get_requires_for_build_wheel(config_settings=None):
    return []


def get_requires_for_build_editable(config_settings=None):
    return []


def prepare_metadata_for_build_wheel(metadata_directory, config_settings=None):
    return _prepare_metadata(metadata_directory)


def prepare_metadata_for_build_editable(metadata_directory, config_settings=None):
    return _prepare_metadata(metadata_directory)


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    return _build(wheel_directory)


def build_editable(wheel_directory, config_settings=None, metadata_directory=None):
    return _build(wheel_directory)
