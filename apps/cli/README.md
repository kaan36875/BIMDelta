# bimdelta

Code review for building models. `bimdelta` compares two versions of an IFC model element by
element and plugs into Git, so `git diff model.ifc` shows which walls, doors and columns changed
instead of thousands of lines of STEP text.

```sh
pip install bimdelta

bimdelta diff rev-a.ifc rev-b.ifc                 # table in the terminal
bimdelta diff rev-a.ifc rev-b.ifc -f markdown     # for a pull request or a report
bimdelta diff rev-a.ifc rev-b.ifc -f json         # the full DiffResult
bimdelta diff rev-a.ifc rev-b.ifc --filter "class=IfcWall*,storey=Level 1"

bimdelta install-git-driver                       # once per clone
git diff HEAD~1 -- model.ifc
bimdelta blame 2O2Fr$t4X7Zf8NOew3FLOH model.ifc   # commits that touched one element
bimdelta quantities rev-a.ifc rev-b.ifc --by material
```

The diff engine is [`bimdelta-core`](https://pypi.org/project/bimdelta-core/), built on
[IfcOpenShell](https://ifcopenshell.org). Documentation:
[CLI reference](https://github.com/kaan36875/BIMDelta/blob/main/docs/cli.md) and
[Git integration](https://github.com/kaan36875/BIMDelta/blob/main/docs/git-integration.md).

Part of [BIMDelta](https://github.com/kaan36875/BIMDelta). MIT licensed.
