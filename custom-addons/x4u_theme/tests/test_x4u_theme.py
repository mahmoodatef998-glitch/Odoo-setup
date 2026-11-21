import base64

from odoo.tests import HttpCase, tagged

from odoo.addons.x4u_theme.controllers.main import EMPTY_PNG

PNG_RED = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
)


@tagged("post_install", "-at_install")
class TestX4uTheme(HttpCase):
    def test_navbar_logo(self):
        """Without an uploaded logo the navbar gets an empty image; with one, that logo."""
        self.authenticate("admin", "admin")
        company = self.env.ref("base.main_company")
        company.x4u_navbar_logo = False
        response = self.url_open("/x4u_theme/navbar_logo")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, EMPTY_PNG)
        company.x4u_navbar_logo = base64.b64encode(PNG_RED)
        response = self.url_open("/x4u_theme/navbar_logo")
        self.assertEqual(response.content, PNG_RED)
        self.assertEqual(response.headers["Content-Type"], "image/png")

    def test_navbar_logo_needs_login(self):
        response = self.url_open("/x4u_theme/navbar_logo", allow_redirects=False)
        self.assertNotEqual(response.status_code, 200)

    def test_login_page(self):
        """The branded login page asks for a username."""
        page = self.url_open("/web/login").text
        self.assertIn("o_x4u_login", page)
        self.assertIn('placeholder="Username or email"', page)
