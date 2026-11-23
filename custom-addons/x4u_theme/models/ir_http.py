from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    def session_info(self):
        """The label of a database that is not the real one (the training database says
        "Training"), shown in the navbar and on the Home page so nobody mixes them up."""
        info = super().session_info()
        info["x4u_environment_label"] = (
            self.env["ir.config_parameter"].sudo().get_param("x4u_theme.environment_label") or ""
        )
        return info
