"""v1.1 on an existing install: the Home page becomes the users' start page."""
from odoo import SUPERUSER_ID, api

from odoo.addons.x4u_theme.hooks import set_home_action


def migrate(cr, version):
    set_home_action(api.Environment(cr, SUPERUSER_ID, {}))
