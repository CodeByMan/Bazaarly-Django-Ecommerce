# Security Policy

This repository is a portfolio learning project and does not accept live payments.

## Reporting

Report suspected vulnerabilities privately to the repository owner. Do not include credentials, raw card data, session cookies, personal data, or database dumps in an issue.

## Secret handling

- Never commit `.env`, database files, private keys, access tokens, or provider credentials.
- Use Stripe test mode only.
- Rotate any value that has been committed, copied into logs, or shared through an untrusted channel.
- Automated tests must mock provider calls and must not access the network.

## Historical incident

Earlier repository state included local configuration and a SQLite database. Those files are removed and ignored in the repaired tree. Their credentials and sessions must still be revoked or invalidated by the credential owners. See `README.md` for the reviewed history-cleanup procedure.
