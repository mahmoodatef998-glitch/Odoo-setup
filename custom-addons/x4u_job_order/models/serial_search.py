"""Spec v0.10 S1-S3: one search box finds a record by a serial (or a PI number) found on it or on
its parts. `ids_for(operator, value)` returns the matching ids for a positive operator."""

POSITIVE = ("ilike", "like", "=", "=ilike", "=like", "in")
NEGATIVE = {"not ilike": "ilike", "not like": "like", "!=": "=", "not in": "in"}


def serial_domain(ids_for, operator, value):
    if operator in NEGATIVE:
        return [("id", "not in", ids_for(NEGATIVE[operator], value))]
    if operator not in POSITIVE or not value:
        return [("id", "=", False)]
    return [("id", "in", ids_for(operator, value))]
