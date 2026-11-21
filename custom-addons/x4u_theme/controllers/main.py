import base64

from odoo import http
from odoo.http import request

# 1 x 1 transparent PNG: the navbar shows nothing when no logo was uploaded.
EMPTY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


class X4uTheme(http.Controller):
    @http.route("/x4u_theme/navbar_logo", type="http", auth="user", readonly=True)
    def navbar_logo(self):
        """The logo on dark of the user's current company."""
        logo = request.env.company.sudo().x4u_navbar_logo
        content = base64.b64decode(logo) if logo else EMPTY_PNG
        return request.make_response(
            content,
            headers=[("Content-Type", "image/png"), ("Cache-Control", "private, max-age=300")],
        )
