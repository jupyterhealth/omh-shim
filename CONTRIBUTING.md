# Contributing to omh-shim

Welcome! `omh-shim` is part of the [JupyterHealth](https://jupyterhealth.org) ecosystem.
As a [Jupyter](https://jupyter.org) project, you can follow the
[Jupyter contributor guide](https://jupyter.readthedocs.io/en/latest/contributing/content-contributor.html).

JupyterHealth is part of the
[JupyterHub subproject](https://jupyterhub-team-compass.readthedocs.io/en/latest/contribute/guide.html).

Make sure to also follow
[Project Jupyter's Code of Conduct](https://github.com/jupyter/governance/blob/HEAD/conduct/code_of_conduct.md)
for a friendly and welcoming collaborative environment.

If you need some help, feel free to ask on
[Zulip](https://jupyter.zulipchat.com/#narrow/channel/469744-jupyterhub/)
or [Discourse](https://discourse.jupyter.org/).

## Development

```bash
pip install -e ".[dev]"   # install with dev tools
pre-commit install        # enable the pre-commit hooks (runs ruff on commit)
```

The same checks run in CI:

```bash
ruff check .              # lint (also runs via pre-commit)
mypy                      # strict type-check
pytest                    # test suite
```

`pre-commit` runs only the fast lint/hygiene hooks; `mypy` and `pytest` stay in
CI. The vendored schemas under `omh_shim/schemas/` are byte-for-byte upstream
copies managed by `tools/refresh_schemas.py` — don't hand-edit or reformat them.
