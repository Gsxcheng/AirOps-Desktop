# Contributing

1. Create a feature branch.
2. Keep changes vendor-neutral unless a driver is based on public vendor documentation.
3. Add or update tests.
4. Run python -m unittest discover -s tests -v.
5. Run python scripts/check_public_safety.py before committing.

Do not include real production data. Example addresses must use RFC 5737
documentation ranges.
