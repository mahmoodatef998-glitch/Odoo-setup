"""Numbering S001 / PO001 / MO001 (x4u_job_order spec v0.4 V1, 2026-10-27). The counters
carry on: an existing database goes on from its next number."""
from odoo import SUPERUSER_ID, api

from odoo.addons.x4u_setup_4u.hooks import set_numbering


def migrate(cr, version):
    set_numbering(api.Environment(cr, SUPERUSER_ID, {}))
