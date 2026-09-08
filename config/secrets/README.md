# Encrypted secret workflow

The private age key is stored outside Git in `/opt/llm-server/.env` as
`SOPS_AGE_KEY`, with mode `0600`. The public recipient in `age.recipient` is
safe to commit.

Encrypt a new runtime secret with:

```bash
set -a; . /opt/llm-server/.env; set +a; \
  sops --encrypt --input-type dotenv --output-type dotenv \
  --output config/secrets/example.enc.env config/secrets/example.env
```

Decrypt only in the controlled deployment environment; never commit plaintext
`*.env` secrets. The candidate security gate runs Gitleaks before a release can
be created.
