"""Spec §19 on an existing install: the Focus account tree (codes, names, groups), the module's
accounts found by their Focus codes, the statements following the selected company."""
from odoo import SUPERUSER_ID, api

from odoo.addons.x4u_account.hooks import x4u_setup


def migrate(cr, version):
    x4u_setup(api.Environment(cr, SUPERUSER_ID, {}))
