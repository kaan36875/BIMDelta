# BIMDelta review action

Comments an element-level summary of IFC model changes on pull requests, with a link that opens
both versions in a 3D diff viewer.

```yaml
- uses: actions/checkout@v4
  with:
    lfs: true
- uses: kaan36875/BIMDelta/apps/github-action@v0.7.0
```

The workflow needs `pull-requests: write`. Inputs, outputs and behaviour for forks, private
repositories and Git LFS: [docs/github-action.md](../../docs/github-action.md).
