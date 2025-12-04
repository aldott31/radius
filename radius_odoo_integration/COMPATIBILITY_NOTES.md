# Compatibility Notes - RADIUS Odoo Integration

## Dummy Fields Issue

### Problem
Early versions of this module included "dummy" Many2many fields (`quotation_document_ids`, `product_document_ids`) to prevent errors when certain Odoo modules were not installed:
- `sale_pdf_quote_builder`
- `documents`

### Why These Were Removed
These dummy fields caused **database migration issues** when:
1. Moving code between servers with different module configurations
2. The target server had `sale_pdf_quote_builder` installed
3. Odoo tried to create relation tables with conflicting structures

### Current Solution
**The dummy fields have been completely removed** from `models/sale_order.py`.

### What This Means
- ✅ **If `sale_pdf_quote_builder` IS installed**: Everything works correctly (the module provides its own fields)
- ✅ **If `sale_pdf_quote_builder` is NOT installed**: You may see JavaScript console warnings, but they won't break functionality
- ✅ **Migration between servers**: No more database constraint conflicts

### If You Need Compatibility
If you absolutely need these dummy fields on a server **without** `sale_pdf_quote_builder`:

1. Install `sale_pdf_quote_builder` module (recommended), OR
2. Add the fields back conditionally (advanced users only)

### Database Cleanup Commands
If you encounter foreign key errors during upgrade:

```bash
# Connect to PostgreSQL
docker exec odoo18_db psql -U odoo -d odoo

# Drop problematic relation tables
DROP TABLE IF EXISTS sale_order_quotation_document_rel CASCADE;
DROP TABLE IF EXISTS sale_order_line_product_document_rel CASCADE;

# Exit and restart Odoo
docker restart odoo18
```

### Affected Files
- `models/sale_order.py` (lines 79-84, 441)

### Date
2025-12-04

### Related Odoo Version
Odoo 18.0
