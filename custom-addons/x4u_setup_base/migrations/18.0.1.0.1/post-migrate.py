"""Lock confirmed sales, credit limit, manual lead enrichment, archive unused defaults (2026-10-21)."""
from odoo import SUPERUSER_ID, api

from odoo.addons.x4u_setup_base.hooks import SETTINGS_V2, apply_settings, archive_unused_defaults


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    apply_settings(env, SETTINGS_V2)
    archive_unused_defaults(env)
