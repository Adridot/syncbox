# Vendored SQLCipher Python binding

This directory contains the complete source from the `sqlcipher3` 0.6.2 source
distribution published on PyPI on 2026-01-07:

- source: `https://files.pythonhosted.org/packages/ae/c1/414003d77549c444bafd636149ab3ace6f4e2cb4666c9955d54ad62096cb/sqlcipher3-0.6.2.tar.gz`;
- SHA-256: `a2b675289ba8889f389625a21f3a01f1ff159a551b5b88fba8fd92da0e02380a`;
- embedded SQLCipher: 4.12.0 Community Edition;
- embedded SQLite: 3.51.1.

The upstream source is redistributed under the Zlib text in `LICENSE`. PyPI's
0.6.2 core metadata instead declares `License-Expression: MIT`; Syncbox records
that upstream metadata discrepancy without inventing a composite expression.
The embedded SQLCipher and SQLite notices are generated into the release
license inventory from their upstream source locations.

## Syncbox modifications

The altered source is plainly identified by this file and the local version
suffix `+syncbox.commoncrypto.1`. Syncbox makes only these build changes:

1. the distribution name is `sqlcipher3-wheels` so it satisfies
   pyrekordbox's existing dependency while continuing to expose the upstream
   `sqlcipher3` module;
2. OpenSSL and Conan build dependencies are removed;
3. `SQLCIPHER_CRYPTO_CC=1` selects SQLCipher's included CommonCrypto provider;
4. the extension links only Apple Security and CoreFoundation frameworks;
5. the macOS deployment target is fixed at 14.0;
6. debug paths/local symbols are omitted and Apple's reproducible linker mode
   is enabled so independent absolute build roots produce identical Mach-O
   bytes;
7. the package is marked private to prevent accidental publication.

No embedded SQLCipher, SQLite, or Python binding C source is modified.
