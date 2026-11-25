"""Spec §21 on an existing install (UAT Phase 3, 2026-11-25): the UAE tax number is printed as TRN.
The VAT Registered box is computed by the upgrade itself: ticked for every UAE contact with a TRN."""
from odoo import SUPERUSER_ID, api

from odoo.addons.x4u_account.hooks import _trn_label


def migrate(cr, version):
    _trn_label(api.Environment(cr, SUPERUSER_ID, {}))
