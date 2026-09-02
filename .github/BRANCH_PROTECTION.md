# GitHub Repository Settings

Configure these settings in the GitHub repository because they cannot be enforced solely by tracked files. `main` is the protected merge target; `develop` is not a required branch unless it is actively reintroduced by maintainers.

## Main branch

- Require pull requests before merging.
- Require at least one approving review and require CODEOWNERS review for owned paths.
- Dismiss stale approvals when new commits are pushed.
- Require all conversations to be resolved.
- Require these status checks: `Frontend Unit & Build`, `Python Tests (api)`, `Python Tests (worker)`, `Python Tests (router)`, `Shared Schema Validation`, `Docker Build Verification`, `Frontend E2E Tests`, `Unified Test Report`, `CYMATIC Deep Integration / integration`, and `CYMATIC Security / scan`.
- Require branches to be up to date before merging.
- Disable force-pushes and branch deletion.
- Enable automatic deletion of head branches after merge.
- Prefer squash merging and disable merge commits.

## Security

- Enable Dependabot security updates and grouped version updates where appropriate.
- Enable secret scanning and push protection.
- Review uploaded SARIF results from Trivy and any future CodeQL workflow.
- Store provider credentials only in GitHub Actions secrets or environment-level secrets.

## Environments

- Keep production deployment approvals separate from pull-request validation.
- Restrict production secrets to protected branches and approved environments.
