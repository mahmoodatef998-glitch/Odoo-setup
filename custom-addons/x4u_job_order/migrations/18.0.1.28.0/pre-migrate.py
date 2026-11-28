"""x4u_reports §2: the letterhead moved to x4u_reports (every document, not only the quotation).

Before the views load, remove the old "4U Letterhead" tab of the company form: it shows the old
image fields, which are gone (their columns are dropped at the end of the update)."""


def migrate(cr, version):
    cr.execute(
        """
        DELETE FROM ir_ui_view
         WHERE id IN (SELECT res_id FROM ir_model_data
                       WHERE module = 'x4u_job_order' AND model = 'ir.ui.view'
                         AND name = 'view_company_form_x4u_letterhead')
        """
    )
    cr.execute(
        """
        DELETE FROM ir_model_data
         WHERE module = 'x4u_job_order' AND model = 'ir.ui.view'
           AND name = 'view_company_form_x4u_letterhead'
        """
    )
