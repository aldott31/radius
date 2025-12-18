from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)

class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    def _check_validity(self):
        """Ensures proper attendance tracking by handling check-ins, check-outs, and preventing overlaps."""
        for attendance in self:
            # Find the last attendance before the current check-in
            last_attendance_before_check_in = self.env['hr.attendance'].search([
                ('employee_id', '=', attendance.employee_id.id),
                ('check_in', '<=', attendance.check_in),
                ('id', '!=', attendance.id),
            ], order='check_in desc', limit=1)

            if last_attendance_before_check_in:
                if last_attendance_before_check_in.check_out and last_attendance_before_check_in.check_out > attendance.check_in:
                    _logger.warning("Employee %s has an overlapping check-in record.", attendance.employee_id.name)

                if not last_attendance_before_check_in.check_out:
                    # Auto-checkout previous record instead of blocking
                    _logger.info("Auto-checkout applied for employee: %s", attendance.employee_id.name)
                    last_attendance_before_check_in.write({'check_out': fields.Datetime.now()})

            # Ensure no duplicate "open" attendances (no check-out)
            open_attendance = self.env['hr.attendance'].search([
                ('employee_id', '=', attendance.employee_id.id),
                ('check_out', '=', False),
                ('id', '!=', attendance.id),
            ], order='check_in desc', limit=1)

            if open_attendance:
                _logger.warning("Employee %s has multiple open check-ins without a check-out. Data may be inconsistent.",
                                attendance.employee_id.name)

            # If this attendance has a check_out, validate overlaps
            if attendance.check_out:
                last_attendance_before_check_out = self.env['hr.attendance'].search([
                    ('employee_id', '=', attendance.employee_id.id),
                    ('check_in', '<', attendance.check_out),
                    ('id', '!=', attendance.id),
                ], order='check_in desc', limit=1)

                if last_attendance_before_check_out and last_attendance_before_check_in != last_attendance_before_check_out:
                    _logger.warning("Employee %s has overlapping attendance records. Manual correction may be needed.",
                                    attendance.employee_id.name)
