# Testing Guide - ministra_manager

## Prerequisites

✅ `ab_ministra_connector` installed and configured
✅ Ministra API credentials configured in Company settings
✅ Test connection successful

## Installation Testing

### 1. Install Module

```bash
# Restart Odoo
# Go to Apps → Search "Ministra IPTV Manager"
# Click Install
```

**Expected:**
- ✅ Module installs without errors
- ✅ New menu "IPTV Management" appears in main menu
- ✅ Security groups created (IPTV User, IPTV Manager)

### 2. Verify Menu Structure

Navigate to: **IPTV Management**

**Expected menu items:**
- ✅ Accounts → IPTV Accounts
- ✅ Configuration → Tariff Plans

## Functional Testing

### Test 1: Sync Tariff Plans

**Steps:**
1. Go to: **IPTV Management → Configuration → Tariff Plans**
2. Click **Sync from Ministra** button
3. Wait for notification

**Expected:**
- ✅ Notification shows "Created: X, Updated: Y"
- ✅ Tariff plans appear in tree view
- ✅ Each tariff has `external_id`, `name`, `ministra_synced=True`
- ✅ Chatter message logged

**Example tariffs (from your server):**
- Premium IPTV
- Basic IPTV
- Standard IPTV

### Test 2: Create IPTV Account Manually

**Steps:**
1. Go to: **IPTV Management → Accounts → IPTV Accounts**
2. Click **New**
3. Fill in:
   - Login: `test_iptv_001`
   - Password: `TestPass123`
   - Full Name: `Test Customer`
   - Tariff Plan: Select any tariff
   - Status: Active (1)
4. Click **Save**
5. Click **Sync to Ministra**

**Expected:**
- ✅ Account created in Odoo
- ✅ "Sync to Ministra" button appears
- ✅ After sync: notification "Sync Successful"
- ✅ `ministra_synced` = True
- ✅ `last_sync_date` populated
- ✅ Chatter message logged

### Test 3: Verify Account in Ministra API

**Manual API Check:**
```bash
# Using curl or browser
curl -u abissnet:abissnet123 \
  http://80.91.126.122:88/stalker_portal/api/accounts/test_iptv_001
```

**Expected JSON:**
```json
{
  "status": "OK",
  "results": [{
    "login": "test_iptv_001",
    "status": 1,
    "tariff_plan": "premium_iptv",
    "full_name": "Test Customer"
  }]
}
```

### Test 4: Pull from Ministra

**Steps:**
1. In Ministra admin panel (or API), change account's `full_name` to "Updated Name"
2. In Odoo, open the account
3. Click **Pull from Ministra**

**Expected:**
- ✅ `full_name` updates to "Updated Name"
- ✅ Other fields update (online, ip, version, etc.)
- ✅ Notification "Pull Successful"
- ✅ Chatter message logged

### Test 5: Quick Provision Wizard

**Steps:**
1. Go to: **IPTV Management → Accounts → IPTV Accounts**
2. Click **Quick Provision** (in toolbar)
3. Fill in:
   - Login: `quick_test_002`
   - Password: Leave empty (auto-generate)
   - Full Name: `Quick Provision Test`
   - Tariff Plan: Select any
   - Auto-sync: Checked
4. Click **Create Account**

**Expected:**
- ✅ Wizard closes
- ✅ Account form opens for new account
- ✅ Password auto-generated (12 characters)
- ✅ If auto-sync=True, account already synced to Ministra
- ✅ `ministra_synced` = True

### Test 6: Send STB Commands

**Steps:**
1. Open an account (must be synced)
2. Click **Reboot STB** button (top right)
3. Confirm

**Expected:**
- ✅ Notification "Reboot Sent"
- ✅ Chatter message "🔄 Reboot command sent to STB"
- ✅ (If STB is online, it should reboot)

**Repeat for:**
- ✅ **Reload Portal** button

### Test 7: Account Status Change

**Steps:**
1. Open an account
2. Change status from "Active (1)" to "Inactive (0)"
3. Click **Sync to Ministra**

**Expected:**
- ✅ Status updated in Odoo
- ✅ Synced to Ministra successfully
- ✅ Verify in API: `status: 0`

### Test 8: Delete from Ministra

**Steps:**
1. Open an account (synced)
2. Click **Delete from Ministra** (header button)
3. Confirm

**Expected:**
- ✅ Notification "Delete Successful"
- ✅ `ministra_synced` = False
- ✅ Account still exists in Odoo
- ✅ Account deleted from Ministra API
- ✅ Chatter message "🗑️ Deleted from Ministra server"

### Test 9: Cron Job - Sync Tariffs

**Steps:**
1. Go to: **Settings → Technical → Automation → Scheduled Actions**
2. Search: "Ministra: Sync Tariff Plans"
3. Click **Run Manually**

**Expected:**
- ✅ Cron runs without error
- ✅ Tariffs updated
- ✅ No errors in logs

### Test 10: Multi-Company Support

**If you have multiple companies:**

**Steps:**
1. Switch to Company B
2. Configure different Ministra API URL (or same with different credentials)
3. Create account in Company B
4. Verify accounts are isolated per company

**Expected:**
- ✅ Company A accounts not visible in Company B
- ✅ Each company can have separate Ministra server
- ✅ No data leakage between companies

## Security Testing

### Test 11: IPTV User (Read-Only)

**Steps:**
1. Create a user with only "IPTV User" group
2. Login as that user
3. Try to:
   - View accounts ✅ (should work)
   - Edit account ❌ (should fail)
   - Delete account ❌ (should fail)
   - Sync to Ministra ❌ (button hidden)

**Expected:**
- ✅ Read-only access enforced
- ✅ No write/delete buttons visible

### Test 12: IPTV Manager

**Steps:**
1. Create user with "IPTV Manager" group
2. Login as that user
3. Try to:
   - Create account ✅
   - Edit account ✅
   - Sync to Ministra ✅
   - Delete from Ministra ❌ (requires Admin)
   - Delete account in Odoo ✅

**Expected:**
- ✅ Full CRUD access
- ✅ Sync buttons visible
- ✅ "Delete from Ministra" button hidden (Admin only)

## Error Handling Testing

### Test 13: Invalid MAC Address

**Steps:**
1. Create account
2. Enter invalid MAC: `INVALID-MAC`
3. Try to save

**Expected:**
- ✅ ValidationError: "Invalid MAC address format"
- ✅ Account not saved

### Test 14: Duplicate Login

**Steps:**
1. Create account with login: `duplicate_test`
2. Try to create another with same login

**Expected:**
- ✅ Error: "Login must be unique per company!"
- ✅ Second account not created

### Test 15: API Connection Failure

**Steps:**
1. In Company settings, change Ministra API URL to invalid
2. Try to sync an account

**Expected:**
- ✅ UserError with connection error
- ✅ `last_sync_error` field populated
- ✅ Error message clear and helpful

### Test 16: Sync Without Required Fields

**Steps:**
1. Create account without login
2. Try to sync

**Expected:**
- ✅ UserError: "Login is required to sync with Ministra"
- ✅ Sync aborted

## Performance Testing

### Test 17: Bulk Account Creation

**Steps:**
1. Create 100+ accounts (via API or import)
2. Monitor database performance
3. Check tree view load time

**Expected:**
- ✅ Tree view loads in < 2 seconds
- ✅ Search works quickly
- ✅ No database locks

### Test 18: Concurrent Sync

**Steps:**
1. Open 5+ accounts in different tabs
2. Click "Sync to Ministra" on all simultaneously

**Expected:**
- ✅ All sync successfully
- ✅ No deadlocks
- ✅ No duplicate API calls

## Integration Testing (Future)

### Test 19: Partner Link (Prep for FAZA 4)

**Steps:**
1. Create a res.partner (contact)
2. Create IPTV account
3. Link partner to account

**Expected:**
- ✅ Partner field populated
- ✅ Link saved correctly

## Regression Testing

After any code changes, rerun:
- ✅ Test 1 (Sync Tariffs)
- ✅ Test 2 (Create Account)
- ✅ Test 3 (Verify in API)
- ✅ Test 5 (Quick Provision)
- ✅ Test 11 (Security)

## Test Results Template

```
Date: ____________
Tester: ____________
Odoo Version: 18.0
Module Version: 18.0.1.0.0

Test Results:
[ ] Test 1: Sync Tariffs - PASS/FAIL
[ ] Test 2: Create Account - PASS/FAIL
[ ] Test 3: API Verification - PASS/FAIL
[ ] Test 4: Pull from Ministra - PASS/FAIL
[ ] Test 5: Quick Provision - PASS/FAIL
[ ] Test 6: STB Commands - PASS/FAIL
[ ] Test 7: Status Change - PASS/FAIL
[ ] Test 8: Delete from Ministra - PASS/FAIL
[ ] Test 9: Cron Job - PASS/FAIL
[ ] Test 10: Multi-Company - PASS/FAIL
[ ] Test 11: IPTV User Security - PASS/FAIL
[ ] Test 12: IPTV Manager Security - PASS/FAIL
[ ] Test 13: Invalid MAC - PASS/FAIL
[ ] Test 14: Duplicate Login - PASS/FAIL
[ ] Test 15: API Failure - PASS/FAIL
[ ] Test 16: Missing Required Fields - PASS/FAIL

Notes:
_________________________________________
_________________________________________
```

## Next Steps

After successful testing of FAZA 2-3:
- ✅ Move to FAZA 4: `ministra_odoo_integration`
- ✅ Integrate with res.partner
- ✅ Add IPTV fields to customer form
- ✅ Bidirectional sync Partner ↔ Account
