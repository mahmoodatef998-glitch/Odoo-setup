from odoo import _, api, models
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.constrains("categ_id", "is_storable", "company_id")
    def _check_x4u_stock_category(self):
        """Spec §20 P1 (UAT 2026-11-24): a product kept in stock is valued in a stock category. In a
        category without automated valuation (All, Saleable...) its bill goes straight to the cost of
        sales, its MO posts nothing and it has no serial: the UAT found CKD, canopies and a ready
        generator in "All". Only the companies with perpetual inventory (Anglo-Saxon) are checked.
        The setup and the tests that build an old (periodic) case pass x4u_any_category."""
        if self.env.context.get("x4u_any_category"):
            return
        Company = self.env["res.company"].sudo()
        Category = self.env["product.category"].sudo()
        for template in self.filtered("is_storable"):
            companies = template.company_id or Company.search([])
            for company in companies.filtered("anglo_saxon_accounting"):
                if template.categ_id.sudo().with_company(company).property_valuation == "real_time":
                    continue
                stock_categories = Category.with_company(company).search([("property_valuation", "=", "real_time")])
                raise ValidationError(
                    _(
                        "%(product)s is kept in stock (Track Inventory), so its category must be a stock "
                        "category: its purchase goes to the inventory, not to the cost of sales, and it is "
                        "tracked by its serial where it should be.\nCategory now: %(category)s.\n"
                        "Pick one of: %(categories)s.",
                        product=template.display_name,
                        category=template.categ_id.display_name,
                        categories=", ".join(stock_categories.mapped("display_name")),
                    )
                )
