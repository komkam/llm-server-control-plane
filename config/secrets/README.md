# Encrypted secret workflow

The private age key is stored outside Git at `/opt/llm-server/config/secrets/age.key`
with mode `0600`. The public recipient in `age.recipient` is safe to commit.

Encrypt a new runtime secret with:

```bash
SOPS_AGE_KEY_FILE=/opt/llm-server/config/secrets/age.key \
  sops --encrypt --input-type dotenv --output-type dotenv \
  --output config/secrets/example.enc.env config/secrets/example.env
```

Decrypt only in the controlled deployment environment; never commit plaintext
`*.env` secrets. The candidate security gate runs Gitleaks before a release can
be created.
