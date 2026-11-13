"""Spec v0.6 R4 (2026-11-10) closed the material request lines of Job Order parts that already got
their stock. Spec v0.8 F3 replaced it: parts are free in stock and a request covers what the
forecast does not, so a database upgraded past 18.0.1.6.0 has nothing to close here."""


def migrate(cr, version):
    return
