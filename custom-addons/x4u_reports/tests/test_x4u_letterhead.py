import base64
import io

from PIL import Image

from odoo.tests import TransactionCase, tagged


def _png():
    out = io.BytesIO()
    Image.new("RGBA", (8, 4), (30, 42, 59, 255)).save(out, "PNG")
    return base64.b64encode(out.getvalue())


@tagged("post_install", "-at_install")
class TestX4uLetterhead(TransactionCase):
    """x4u_reports §2: every document printed with the company's layout carries the letterhead."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.layout = cls.env.ref("x4u_reports.report_layout_x4u")
        image = _png()
        cls.company.write(
            {
                "external_report_layout_id": cls.layout.view_id.id,
                "x4u_lh_name": "ACME TRADING (FZC)",
                "x4u_lh_tagline": "EQUIPMENT TRADING",
                "x4u_lh_name_ar": "أكمي للتجارة",
                "x4u_lh_tagline_ar": "تجارة المعدات",
                "x4u_lh_contact": "Tel: +000 0 000 0000, E-mail: info@example.com, TRN: 000000000000000",
                "x4u_lh_logo": image,
                "x4u_lh_watermark": image,
                "x4u_lh_brands": image,
            }
        )

    def _html(self, company):
        html, _kind = (
            self.env["ir.actions.report"]
            .with_company(company)
            ._render_qweb_html("web.preview_externalreport", company.ids)
        )
        return html.decode()

    def test_layout_is_offered(self):
        """The 4U Letterhead is a document layout of its own, first in the list."""
        layouts = self.env["report.layout"].search([])
        self.assertIn(self.layout, layouts)
        self.assertEqual(layouts[0], self.layout)

    def test_letterhead_on_the_document(self):
        """Names in English and Arabic, the contact line, the logo and the brands."""
        html = self._html(self.company)
        for text in ("ACME TRADING (FZC)", "EQUIPMENT TRADING", "أكمي للتجارة", "تجارة المعدات", "info@example.com"):
            self.assertIn(text, html)
        for css in ("o_x4u_lh_header", "o_x4u_lh_logo", "o_report_layout_x4u", "o_x4u_lh_brands"):
            self.assertIn(css, html)
        # The watermark is for the PDF pages only, not the preview in the browser.
        self.assertNotIn("o_x4u_lh_watermark", html)

    def test_contact_line_from_the_company(self):
        """No contact line typed: phone, mobile, email, address and Tax ID of the company."""
        self.company.write(
            {
                "x4u_lh_contact": False,
                "phone": "+000 1",
                "mobile": "+000 2",
                "email": "office@example.com",
                "street": "Unit 1",
                "city": "Sharjah",
                "vat": "100000000000003",
            }
        )
        line = self.company._x4u_lh_contact_line()
        for text in ("Tel: +000 1", "Mob: +000 2", "E-mail: office@example.com", "Unit 1", "Sharjah", "100000000000003"):
            self.assertIn(text, line)

    def test_company_without_letterhead(self):
        """A company with no letterhead (e.g. ATA) prints with Odoo's standard layout."""
        other = self.env["res.company"].create(
            {"name": "Other Co", "external_report_layout_id": self.layout.view_id.id}
        )
        self.assertFalse(other.x4u_lh_ready)
        html = self._html(other)
        self.assertNotIn("o_x4u_lh_header", html)
        self.assertIn("o_report_layout_standard", html)
