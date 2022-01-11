# pytkdocs_tweaks

Some custom tweaks for [pytkdocs](https://github.com/mkdocstrings/pytkdocs).

_For use as part of the documentation-generation-for-Python stack that comprises [mkdocs](https://www.mkdocs.org/), [mkdocs-material](https://github.com/squidfunk/mkdocs-material), [mkdocstrings](https://github.com/mkdocstrings/mkdocstrings/) and [pytkdocs](https://github.com/mkdocstrings/pytkdocs)._

- Types are ubiquitously displayed in the way you import them: `package.Foo` (rather than being a mix of where they're defined: `package.subpackage.foomodule.Foo` or just their name: `Foo`).
- Only public base classes are shown (rather than every base class).
- Adds short documentation for inherited and implemented methods, e.g. "Inherited from `package.Foo`." (Rather than nothing at all.)
    - An inherited method is one inherited from a base class. An implemented method is one overriding an abstract method on a base class.
- Sets a custom `typing.GENERATING_DOCUMENTATION = True` flag that you can use to detect when documentation generation is happening and customise things if desired (documentation generation imports the library you're documenting).
- Adds an `abstractmethod`/`abstractproperty` property to appear in the documentation instead. (Useful when specifying abstract base classes.)
- Removed the `dataclass` and `special` properties that appear in the documentation. (I find that these just add visual noise.)
- Removed the `-> None` return annotation on `__init__` methods.

Note that you must run the `mkdocs` command twice, as these custom tweaks write a cache to disk -- listing all the public objects -- that are then used on the second run. If you see a `.all_objects.cache` file appear -- this is why. (You may wish to add the file to your `.gitignore`.)

## Installation

```bash
pip install pytkdocs_tweaks
```

Requires Python 3.8+ and `pytkdocs>=0.15.0`.

## Usage

In your `mkdocs.yml`:

```
plugins:
    - search  # default plugin, need to re-enable when using manual plugins
    - mkdocstrings:
        handlers:
            python:
                setup_commands:
                    - import pytkdocs_tweaks
                    - pytkdocs_tweaks.main()
                selection:
                    inherited_members: true  # allow looking up inherited members
                rendering:
                    show_root_heading: true    #
                    show_root_full_path: true  # have e.g. `package.Foo` display correctly, rather than e.g. just `Foo`.
```
