from odoo import models, fields,api

class ProjectTask(models.Model):
    _inherit = 'project.task'

    department_ids = fields.Many2many(
        'hr.department',
        string="Allowed Departments",
        help="Departments allowed to see this task."
    )

    @api.model
    def _filter_tasks_by_assignee_or_department(self):
        """
        Restrict project tasks visibility:
        1️⃣ If the task has Assignees (`user_ids`), only assigned users can see it.
        2️⃣ If there are no Assignees, use `department_ids` to control access.
        3️⃣ Admins & Project Managers bypass restrictions and see all tasks.
        """
        user = self.env.user

        # 1️⃣ Admins & Project Managers get full access
        if user.has_group('base.group_system') or user.has_group('project.group_project_manager'):
            return []

        # 2️⃣ If user is assigned to the task, allow access
        return ['|',
                ('user_ids', 'in', [user.id]),
                ('department_ids', 'in', user.employee_id.department_id.ids)]

    def _get_access_rules(self):
        """Returns the computed domain for access rules."""
        return self._filter_tasks_by_assignee_or_department()