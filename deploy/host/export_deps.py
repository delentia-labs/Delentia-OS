"""Print the project's dependencies (pyproject.toml `dependencies` plus the `full` extra), one per line.

The host Dockerfile installs these in their own layer, before the source is copied, so an edit to the source does not reinstall
several GB of wheels. `pip install -e ".[full]"` used to do the same job but needed the source tree, which is what made the layer
depend on every .py file.
"""
import sys
import tomllib

with open(sys.argv[1] if len(sys.argv) > 1 else "pyproject.toml", "rb") as handle:
    project = tomllib.load(handle)["project"]
print("\n".join(project["dependencies"] + project["optional-dependencies"]["full"]))
