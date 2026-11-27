# Experimental prepared-quotation projection (not production)

This branch contains an opt-in offline prototype under tools. It does not
change the regular kit, its schemas, its publication path or normative copies.
Input: actual signed translation-unit packet, its ordinary draft unit patch,
and trusted local results of CitationRegistry.reconstruct from the resolver.
The adapter verifies the exact source parameter identity and quote/receipt
hashes, hides prepared rows in both the French and English views and draft
patch, and retains their full source/target identity in a private manifest.
The model only receives the projected files, not that manifest or the original
packet. Existing populated target rows or changed source locks are skipped.

After editing, restore inserts the exact selected published English fragments
at their original citation IDs and order, with source parameters preserved.
Rows and units remain pending, no editorial attestation is fabricated,
and ordinary kit scope checks still apply. The projection has separate
schemas and must never be submitted directly to seal/apply. In particular,
the current kit still uses an AI translation warning and preserves the French
reference link; a published-translation provenance and rights policy must
be integrated before using these rows in final publication.

Run the targeted tests using:
    PYTHONPATH=kit/scripts:tools python -m pytest -q tools/test_experimental_prepared_citations.py

The local receipt digest is an integrity check, not authentication. The
trusted caller must actually reconstruct the passages from the resolver,
check current documentary evidence, and keep all private material out of Git.
Byte counts compare serialized data only, not provider billing or quota.
