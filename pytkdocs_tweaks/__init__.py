import argparse
import importlib
import inspect
import json
import pathlib
import sys
import traceback
import typing
import warnings
from typing import Any, Dict

import pytkdocs
import pytkdocs.cli
import pytkdocs.serializer


__version__ = "0.0.5"


_cachefile = pathlib.Path(".all_objects.cache")


def _populate_cache(data: Dict[str, Any], cache: Dict[str, str], path: str):
    cache[data["path"]] = path
    for child in data["children"].values():
        _populate_cache(child, cache, path + "." + child["name"])


def _str_to_obj(string: str) -> Any:
    pieces = string.split(".")
    if len(pieces) == 1:
        # Not a relative module.class lookup.
        # Must be a builtin.
        return None
    obj = importlib.import_module(pieces[0])
    for piece in pieces[1:]:
        obj = getattr(obj, piece)
    return obj


def _obj_to_str(obj: Any) -> str:
    module = obj.__module__
    name = obj.__qualname__
    if module == "builtins":
        return name
    else:
        return module + "." + name


def _find_public_bases(bases, cache):
    out = []
    for base in bases:
        if base in cache.keys():
            out.append(base)
        else:
            base_obj = _str_to_obj(base)
            if base_obj is not None:
                base_bases = [_obj_to_str(b) for b in base_obj.__bases__]
                for _base in _find_public_bases(base_bases, cache):
                    out.append(_base)
    out = list(dict.fromkeys(out))  # remove repeats
    return out


def _postprocess(data, cache, bases):
    #
    # Very important: update the displayed path for each doc item to being in "import
    # form" rather than "full form".
    #
    data["path"] = cache[data["path"]]

    #
    # By default str(Optional[Foo]), str(Tuple[Foo]) etc. uses
    # Foo.__module__ + "." + Foo.__qualname__
    # to produce e.g.
    # "Optional[package.module.Foo]"
    # However str(Foo) just produces "Foo".
    # We fix this inconsistency here.
    #

    try:
        signature = data["signature"]
    except KeyError:
        pass
    else:
        for parameter in signature["parameters"]:
            if "annotation" in parameter:
                for p in cache:
                    parameter["annotation"] = parameter["annotation"].replace(
                        p, p.rsplit(".", 1)[1]
                    )
        if "return_annotation" in signature:
            for p in cache:
                signature["return_annotation"] = signature["return_annotation"].replace(
                    p, p.rsplit(".", 1)[1]
                )

    if "bases" in data:
        # Find those base classes which are part of our public documentation.
        # This is used for a couple of things lower down.
        bases = _find_public_bases(data["bases"], cache)

        # Display base classes in "import form" not "full form".
        data["bases"] = [cache[base] for base in bases]

    #
    # Remove some properties we don't want to display; this reduces visual noise.
    #
    for prop in ("dataclass", "special"):
        try:
            data["properties"].remove(prop)
        except ValueError:
            pass

    #
    # Add on some extra properties.
    #
    try:
        obj = _str_to_obj(data["path"])
    except AttributeError:
        pass
        # Can happen when doing:
        #
        # @dataclass
        # class A:
        #       myfield: int
        #
        # and then trying to access `A.myfield`.
        # This doesn't actually exist on the class object -- only on instances.
        # Which means that the _str_to_obj line will fail.
    else:
        if getattr(obj, "__isabstractmethod__", False):
            if "property" in data["properties"]:
                data["properties"] = [
                    "abstractproperty" if x == "property" else x
                    for x in data["properties"]
                ]
            else:
                data["properties"].append("abstractmethod")
        del obj

    #
    # Add documentation pointing towards base classes that we inherit methods from, or
    # implement abstractmethods of.
    #
    new_docstring = ""
    if "inherited" in data["properties"]:
        for base in bases:
            if data["name"] in _str_to_obj(base).__dict__:
                new_docstring = f"Inherited from [`{cache[base]}.{data['name']}`][]."
                break
        else:
            _base_obj = _str_to_obj(data["path"])
            _base_path = _base_obj.__module__ + "." + _base_obj.__qualname__
            _base_config = {"objects": [{"path": _base_path}]}
            _base_result = pytkdocs.cli.process_config(_base_config)
            new_docstring = _base_result["objects"][0]["docstring"]
            data["properties"].remove("inherited")
    if bases is not None:
        for base in bases:
            _base_obj = _str_to_obj(base)
            if data["name"] in _base_obj.__dict__:
                base_method = getattr(_base_obj, data["name"])
                if getattr(base_method, "__isabstractmethod__", False):
                    if (
                        data["docstring"] == inspect.getdoc(base_method)
                        or data["docstring"] == ""
                        or data["docstring"] is None
                    ):
                        new_docstring = (
                            f"Implements [`{cache[base]}.{data['name']}`][]."
                        )
                        break
    if new_docstring != "":
        data["docstring_sections"] = [{"type": "markdown", "value": new_docstring}]
        # We're modifying docstring_sections, so del docstring as an assertion that
        # it's not used downstream (and that we're not inconsistent as a result).
        del data["docstring"]

    #
    # Don't display "-> None" annotations on __init__ methods.
    #
    if data["name"] == "__init__":
        data["signature"].pop("return_annotation", None)

    # Recurse into methods of classes, etc.
    for child in data["children"].values():
        _postprocess(child, cache, bases)


def main():
    # Monkey-patch process_config to modify how objects are displayed.
    #
    # Note that this uses a cache file written to disk -- this cache is used to keep
    # track of a list of mappings from "full form" to "import form", where e.g.
    # full form: package.subpackage.module.foo
    # import form: package.foo
    # due to package/__init__.py importing foo so as to expose it publicly.
    # "Full form" is used ubiquitously throughout mkdocstrings, and this allows us to
    # convert it to the more-readable "import form" (which is how one should actually
    # be using each foo).
    #
    # In addition this cache performs double-duty as a record of all public objects.
    #
    # As such to get accurate documentation this should be run twice: once to generate
    # the cache, and a second time to use it. (Although in practice a lot of the cache
    # will often get populated before the entry is needed on a first run.)

    _process_config = pytkdocs.cli.process_config

    def process_config(config):
        paths = [c["path"] for c in config["objects"]]
        datas = _process_config(config)
        with _cachefile.open() as f:
            cache = json.load(f)
        for path, data in zip(paths, datas["objects"]):
            _populate_cache(data, cache, path)
            try:
                _postprocess(data, cache, bases=None)
            except Exception as e:
                tb = traceback.format_exc()
                warnings.warn(
                    f"When loading {data['name']}, an exception of type "
                    f"{type(e)} was raised, with message '{str(e)}' and "
                    f"traceback:\n{tb}."
                )
        with _cachefile.open("w") as f:
            json.dump(cache, f)
        return datas

    if not _cachefile.exists():
        with _cachefile.open("w") as f:
            json.dump({}, f)

    pytkdocs.cli.process_config = process_config

    _serialize_signature_parameter = pytkdocs.serializer.serialize_signature_parameter

    def serialize_signature_parameter(parameter):
        out = _serialize_signature_parameter(parameter)
        if inspect.isfunction(parameter.default):
            assert "default" in out
            out["default"] = f"<function {parameter.default.__name__}>"
        return out

    pytkdocs.serializer.serialize_signature_parameter = serialize_signature_parameter

    # By default pytkdocs has some really weird behaviour in which the docstring for
    # inherited magic methods are removed. This removes that behaviour.
    pytkdocs.loader.RE_SPECIAL = argparse.Namespace(match=lambda _: False)

    # Set a flag to say we're generating documentation, which the library can use to
    # customise how its types are displayed.
    typing.GENERATING_DOCUMENTATION = True
