# foundry-handwritten-docs

Project to assess capability of Foundry to ingest mixed documents with printed and hand-written notes and append the handwritten content in the document.

> [!NOTE]
> This is a personal project, shared as is to help others. It is not an official Microsoft
> product and is not supported by Microsoft. Review and test it before using any part of it
> in your environment. See [docs/SUPPORT.md](docs/SUPPORT.md).

## Overview

<!-- Keep this section: a few lines on what the project does and for whom. The details go in
     docs/architecture.md. -->

Forms and reports often mix printed text with handwritten notes. This project tests how well
Microsoft Foundry and Azure Document Intelligence can read that handwriting, and builds a local
tool to put it back into the document as typed text, safely:

- **Handwriting CLI** (`src/handwritten_docs/`): an offline Python tool that inspects a PDF,
  places recorded recognition results on its pages, lets a person review and approve each
  replacement, and exports a new PDF. Only `inspect` is available so far
  ([docs/handwriting-cli.md](docs/handwriting-cli.md)).
- **Azure infrastructure** (`infra/`): azd and Bicep for the Foundry and Document Intelligence
  resources, private by default. Nothing is deployed until it is approved.

## Quick start

<!-- Keep this section: the few commands that take a new user from a clone to a first
     preview or deployment, each with where it runs. The full walkthrough stays in
     docs/getting-started.md. -->

## Contents

<!-- Keep this README short: the Overview and Quick start above, then this table of contents of
     the pages. Background, how-tos and long explanations go in docs/, one page per topic. -->

**Use it**

| Page | What it covers |
|---|---|
| [docs/handwriting-cli.md](docs/handwriting-cli.md) | The handwriting CLI: set up, commands, settings, tests |
| [docs/getting-started.md](docs/getting-started.md) | **Start here** for the infrastructure: local tenant files, a first environment and preview, profiles, adding resources, tests |
| [docs/architecture.md](docs/architecture.md) | The conventions layer, profiles, network, naming contract, extension points |
| [docs/configuration.md](docs/configuration.md) | Profiles, environment values, preflight, expert overrides, resource naming |
| [docs/deployment.md](docs/deployment.md) | Prerequisites and roles, prepare → validate → deploy, Bastion access, cost and teardown |
| [docs/modules.md](docs/modules.md) | The module catalog and its lifecycle scripts |
| [docs/security.md](docs/security.md) | Public exceptions, private DNS, monitoring access, break glass |
| [docs/ci-cd.md](docs/ci-cd.md) | CI, PR rules, public logs and the repository settings |
| [docs/ci-deployment.md](docs/ci-deployment.md) | Pull request deployments into throwaway environments |
| [docs/supply-chain.md](docs/supply-chain.md) | Package feeds, lock files and the 7-day age gate |
| [docs/database.md](docs/database.md) | Database changes: migration, backup, way back |
| [docs/SUPPORT.md](docs/SUPPORT.md) | Questions, bugs, and what support to expect |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | Changes |
| [docs/template.md](docs/template.md) | What the template contains and how a new project is set up |

**Contribute**

Every change starts with an issue, gets its own `<type>/<issue>-<slug>` branch, and reaches
`main` only through a PR that closes the issue.

| Page | What it covers |
|---|---|
| [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md), [docs/CODE_OF_CONDUCT.md](docs/CODE_OF_CONDUCT.md) | How to contribute |
| [.github/copilot-instructions.md](.github/copilot-instructions.md), [.github/instructions/](.github/instructions/) | The full rules, for people and AI coding assistants, and the per-language ones |
| [docs/decisions/](docs/decisions/) | Decision records |
| [.github/SECURITY.md](.github/SECURITY.md) | Reporting a vulnerability |

## License

[MIT](LICENSE)
