# redefine-aws-serverless-workflow

Reusable GitHub Actions workflows for the [Redefine AWS Serverless](https://github.com/topics/redefine-aws-serverless)
series. Public because GitHub only lets public repositories call reusable workflows from public repositories.

- `reusable-test.yml` — pytest, optional reference service from the project's `tests/compat/docker-compose.yml`,
  uploads `tests/compat/REPORT.md`
- `reusable-publish.yml` — tag == version check, build `client/`, PyPI trusted publishing

A project calls them with `uses: cloudformer/redefine-aws-serverless-workflow/.github/workflows/reusable-test.yml@main`
(see the project template's `.github/workflows/test.yml` / `publish.yml`). Change CI here once, every project follows.
