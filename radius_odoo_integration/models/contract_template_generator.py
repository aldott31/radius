# -*- coding: utf-8 -*-
"""
Contract Template Generator
Handles generation of contract documents from templates
"""
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
import base64
import io

_logger = logging.getLogger(__name__)


class ContractTemplateGenerator(models.AbstractModel):
    """
    Abstract model for generating contracts from templates
    Supports both DOCX templates and fallback to PDF
    """
    _name = 'contract.template.generator'
    _description = 'Contract Template Generator'

    def _get_template_path(self):
        """
        Get the path to the contract template file
        Templates should be stored in: radius_odoo_integration/templates/contracts/
        """
        import os
        addon_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        template_path = os.path.join(addon_path, 'templates', 'contracts', 'contract_template.docx')
        return template_path

    def _prepare_contract_data(self, contract):
        """
        Prepare data dictionary for template placeholders

        Args:
            contract: customer.contract record

        Returns:
            dict: Dictionary with all contract data for template
        """
        # Format date
        contract_date = contract.data.strftime('%d/%m/%Y') if contract.data else ''

        # Format afati/pagesa
        afati_text = dict(contract._fields['afati'].selection).get(contract.afati, '') if contract.afati else ''
        pagesa_text = 'Parapagim' if contract.pagesa == 'prepaid' else 'Paspagim' if contract.pagesa == 'postpaid' else ''

        # Format lloji_lidhjes
        lloji_lidhjes_text = dict(contract._fields['lloji_lidhjes'].selection).get(contract.lloji_lidhjes, '') if contract.lloji_lidhjes else ''

        # Format IP type
        ip_statike_text = 'IP Statike - Po' if contract.ip_statike == 'no' else 'Dinamike'

        # Muaji paguar checkboxes (1-12)
        muaji_paguar = {}
        for i in range(1, 13):
            if contract.pagesa == 'prepaid' and contract.prepaid_months:
                muaji_value = contract.prepaid_months
                muaji_paguar[f'muaj_{i}'] = '■' if i <= muaji_value else '□'
            else:
                muaji_paguar[f'muaj_{i}'] = '□'

        # Prepare equipment lists
        cpe_internet_names = ', '.join(contract.cpe_internet_product_ids.mapped('name')) if contract.cpe_internet_product_ids else ''
        router_wifi_names = ', '.join(contract.router_wifi_product_ids.mapped('name')) if contract.router_wifi_product_ids else ''
        cpe_tv_names = ', '.join(contract.cpe_tv_product_ids.mapped('name')) if contract.cpe_tv_product_ids else ''

        # Build data dictionary
        data = {
            # Header info
            'contract_date': contract_date,
            'contract_number': contract.name or '',
            'afati_pagesa': f"{afati_text} / {pagesa_text}",
            'penaliteti': 'referuar Pikës 5.1',
            'nr_perdoruesit': contract.partner_id.radius_username or '',

            # Muaji paguar checkboxes
            **muaji_paguar,

            # Individual customer info
            'emri_individ': contract.emri or '' if contract.tipi_kontrates == 'individ' else '',
            'nr_personal': contract.nr_personal or '' if contract.tipi_kontrates == 'individ' else '',
            'id_number': contract.id_number or '' if contract.tipi_kontrates == 'individ' else '',
            'datelindja': contract.datelindja.strftime('%d/%m/%Y') if contract.datelindja and contract.tipi_kontrates == 'individ' else '',
            'vendlindja': contract.vendlindja or '' if contract.tipi_kontrates == 'individ' else '',
            'adresa_individ': contract.adresa_1 or '' if contract.tipi_kontrates == 'individ' else '',
            'mobile_individ': contract.mobile_1 or '' if contract.tipi_kontrates == 'individ' else '',
            'email_individ': contract.email or '' if contract.tipi_kontrates == 'individ' else '',

            # Business customer info
            'emri_kompanie': contract.emri or '' if contract.tipi_kontrates != 'individ' else '',
            'nuis': contract.partner_id.vat or '' if contract.tipi_kontrates != 'individ' else '',
            'adresa_kompanie': contract.adresa_1 or '' if contract.tipi_kontrates != 'individ' else '',
            'perfaqesuesi_ligjor': contract.perfaqesuesi_ligjor or '' if contract.tipi_kontrates != 'individ' else '',
            'nr_personal_perfaqesues': contract.nr_personal_perfaqesues or '' if contract.tipi_kontrates != 'individ' else '',
            'mobile_kompanie': contract.mobile_1 or '' if contract.tipi_kontrates != 'individ' else '',
            'email_kompanie': contract.email or '' if contract.tipi_kontrates != 'individ' else '',

            # Services
            'lloji_lidhjes': lloji_lidhjes_text,
            'cmimi_lloji_lidhjes': f"$ {contract.cmimi_lloji_lidhjes:,.2f}" if contract.cmimi_lloji_lidhjes else '$ 0.00',

            'sherbimi_internet': contract.emri_planit_internet or '',
            'cmimi_internet': f"$ {contract.cmimi_planit:,.2f}" if contract.cmimi_planit else '$ 0.00',

            'sherbimi_tv': contract.emri_planit_tv or '',
            'cmimi_tv': f"$ {contract.cmimi_teknologjia_tv:,.2f}" if contract.cmimi_teknologjia_tv else '$ 0.00',

            'sherbimi_telefonik': contract.emri_planit_telefon or '',
            'cmimi_telefonik': '',  # Not stored

            'lloji_ip': ip_statike_text,
            'cmimi_ip': f"$ {contract.cmimi_ip_statike:,.2f}" if contract.cmimi_ip_statike else '$ 0.00',

            'pajisje_internet': cpe_internet_names,
            'cmimi_pajisje_internet': f"$ {contract.cmimi_cpe_internet:,.2f}" if contract.cmimi_cpe_internet else '$ 0.00',

            'pajisje_tv': cpe_tv_names,
            'cmimi_pajisje_tv': f"$ {contract.cmimi_cpe_tv:,.2f}" if contract.cmimi_cpe_tv else '$ 0.00',

            'router_wifi': router_wifi_names,
            'cmimi_router_wifi': f"$ {contract.cmimi_router_wifi:,.2f}" if contract.cmimi_router_wifi else '$ 0.00',

            'total': f"$ {contract.cmimi_total:,.2f}" if contract.cmimi_total else '$ 0.00',

            # Total months paid (price × prepaid months)
            'total_muaj_paguar': f"$ {(contract.cmimi_total * (contract.prepaid_months or 0)):,.2f}",

            # Comments
            'comment': contract.comment or '',
        }

        return data

    def generate_contract_document(self, contract):
        """
        Generate contract document from template

        Args:
            contract: customer.contract record

        Returns:
            tuple: (filename, file_content_base64)
        """
        try:
            # Try to use DOCX template if python-docx-template is available
            return self._generate_from_docx_template(contract)
        except ImportError:
            _logger.warning("python-docx-template not installed, falling back to PDF")
            return self._generate_from_pdf_report(contract)
        except FileNotFoundError:
            _logger.warning("DOCX template not found, falling back to PDF")
            return self._generate_from_pdf_report(contract)
        except Exception as e:
            _logger.error("Error generating contract from template: %s", str(e))
            return self._generate_from_pdf_report(contract)

    def _generate_from_docx_template(self, contract):
        """
        Generate DOCX document from template using python-docx-template

        Args:
            contract: customer.contract record

        Returns:
            tuple: (filename, file_content_base64)
        """
        import os
        from docxtpl import DocxTemplate

        # Get template path
        template_path = self._get_template_path()
        if not os.path.exists(template_path):
            raise FileNotFoundError(f"Template not found: {template_path}")

        # Load template
        doc = DocxTemplate(template_path)

        # Prepare data
        context = self._prepare_contract_data(contract)

        # Render document
        doc.render(context)

        # Save to BytesIO
        output = io.BytesIO()
        doc.save(output)
        output.seek(0)

        # Encode to base64
        file_content = base64.b64encode(output.read())
        filename = f"Contract_{contract.name}.docx"

        return filename, file_content

    def _generate_from_pdf_report(self, contract):
        """
        Fallback: Generate PDF from existing QWeb report

        Args:
            contract: customer.contract record

        Returns:
            tuple: (filename, file_content_base64)
        """
        # Use ir.actions.report to render PDF
        report = self.env['ir.actions.report']

        # Render PDF directly with report name and IDs
        pdf_content, _ = report._render_qweb_pdf(
            report_ref='radius_odoo_integration.report_customer_contract_document',
            res_ids=contract.ids
        )

        file_content = base64.b64encode(pdf_content)
        filename = f"Contract_{contract.name}.pdf"

        return filename, file_content
