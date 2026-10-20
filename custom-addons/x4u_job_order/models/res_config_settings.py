from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    x4u_purchase_user_id = fields.Many2one(
        "res.users", string="Purchasing Officer", config_parameter="x4u_job_order.purchase_user_id"
    )
    x4u_warehouse_user_id = fields.Many2one(
        "res.users", string="Storekeeper", config_parameter="x4u_job_order.warehouse_user_id"
    )
    x4u_qc_user_id = fields.Many2one("res.users", string="Quality Inspector", config_parameter="x4u_job_order.qc_user_id")
    # Target days per stage; 0 = no target (spec §7.3: measure first, then set).
    x4u_target_purchasing_days = fields.Float(config_parameter="x4u_job_order.target_purchasing_days")
    x4u_target_approval_days = fields.Float(config_parameter="x4u_job_order.target_approval_days")
    x4u_target_supplier_days = fields.Float(config_parameter="x4u_job_order.target_supplier_days")
    x4u_target_warehouse_days = fields.Float(config_parameter="x4u_job_order.target_warehouse_days")
    x4u_target_assembly_days = fields.Float(config_parameter="x4u_job_order.target_assembly_days")
    x4u_target_qc_days = fields.Float(config_parameter="x4u_job_order.target_qc_days")
    x4u_target_dispatch_days = fields.Float(config_parameter="x4u_job_order.target_dispatch_days")

    def set_values(self):
        super().set_values()
        self.env["mrp.production"].sudo()._cron_x4u_update_delays()
