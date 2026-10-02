# Security policy

## Supported versions

Security fixes are provided for the latest published `1.x` release. Older
builds should be updated before a report is reproduced.

## Reporting a vulnerability

Please use [GitHub's private vulnerability report](https://github.com/codingdosic/nodeMacro/security/advisories/new).
If that form is unavailable, email [yanche2990@gmail.com](mailto:yanche2990@gmail.com).
Do not publish a vulnerability that could expose user data or allow unintended
local actions.

Include the D5 Macro version, Windows version, reproduction steps, expected
impact, and whether the issue works without local user interaction. Remove
passwords, captured images, macro contents, logs, and other personal data that
are not necessary to reproduce the issue.

## Security model

D5 Macro serves its editor only on `127.0.0.1`, does not provide a remote
account service, and does not send telemetry. Saved macros can reproduce input
and launch programs or URLs, so macro JSON and generated batch files must be
treated like executable files. Only run scripts from a trusted source.
