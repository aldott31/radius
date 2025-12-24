# Ministra IPTV Manager

**Version:** 18.0.1.0.0
**Author:** Abissnet
**License:** LGPL-3

## Overview

Core IPTV account and tariff management module for Ministra (Stalker) platform integration.

## Features

### 📊 Tariff Management
- Sync tariff plans from Ministra API
- Auto-update via daily cron job
- View active accounts per tariff
- Support for multiple companies

### 👤 Account Management
- Create/Update/Delete IPTV accounts
- Bidirectional sync with Ministra server
- STB (Set-Top Box) information tracking
- Online/Offline status monitoring
- Quick provision wizard

### 🎬 STB Control
- Send reboot command to STB
- Reload portal command
- Real-time status updates

## Dependencies

- `base` - Odoo base module
- `mail` - Mail/Chatter integration
- `ab_ministra_connector` - Ministra API connector

## Installation

1. Install `ab_ministra_connector` first
2. Configure Ministra API credentials in Company settings
3. Install `ministra_manager`
4. Sync tariff plans from Ministra
5. Start creating IPTV accounts

## Configuration

### 1. Configure API Connection

Go to: **Settings → Companies → Your Company → Ministra IPTV Tab**

- **API Base URL:** `http://80.91.126.122:88/stalker_portal/api`
- **Username:** `abissnet`
- **Password:** `abissnet123`
- Click **Test Ministra** to verify connection

### 2. Sync Tariff Plans

Go to: **IPTV Management → Configuration → Tariff Plans**

- Click **Sync from Ministra**
- Verify tariffs imported successfully

### 3. Create IPTV Account

**Option A: Manual Creation**
- Go to: **IPTV Management → Accounts → IPTV Accounts**
- Click **New**
- Fill in login, password, tariff plan
- Click **Sync to Ministra**

**Option B: Quick Provision Wizard**
- Click **Quick Provision** button
- Fill in account details
- Auto-sync enabled by default

## Usage

### Account Lifecycle

1. **Create Account** - Account created in Odoo (not synced)
2. **Sync to Ministra** - Push to Ministra server (status=inactive)
3. **Activate** - Set status=1 and sync again
4. **Monitor** - Pull from Ministra to get online status
5. **Deactivate/Delete** - Set status=0 or delete from Ministra

### Sync Operations

- **Sync to Ministra:** Push Odoo data → Ministra (POST/PUT)
- **Pull from Ministra:** Pull Ministra data → Odoo (GET)
- **Delete from Ministra:** Remove account from Ministra (DELETE)

### STB Commands

- **Reboot STB:** Send reboot event to customer's STB
- **Reload Portal:** Refresh portal on STB

## Security Groups

- **IPTV User:** Read-only access to accounts and tariffs
- **IPTV Manager:** Full CRUD access, can sync with Ministra
- **Ministra Admin:** (from ab_ministra_connector) Full admin access including delete

## Cron Jobs

- **Sync Tariff Plans:** Daily at 02:00 AM (configurable)

## Models

### ministra.tariff
- Tariff plans synced from Ministra
- Fields: external_id, name, days_to_expires, etc.

### ministra.account
- IPTV customer accounts
- Fields: login, password, stb_mac, tariff_plan, status, etc.
- Methods: action_sync_to_ministra(), action_pull_from_ministra(), action_delete_from_ministra()

## API Integration

All API calls use `res.company.ministra_api_call()` from `ab_ministra_connector`.

### Endpoints Used

- `GET /tariffs` - Sync tariff plans
- `GET /accounts/{login}` - Pull account data
- `POST /accounts/` - Create account
- `PUT /accounts/{login}` - Update account
- `DELETE /accounts/{login}` - Delete account
- `POST /send_event/{login}` - Send events (reboot, reload_portal)

## Roadmap (Future Modules)

- `ministra_odoo_integration` - Sales/Payment integration
- Channel management
- Subscription packages
- Advanced monitoring dashboard

## Support

For issues or questions, contact Abissnet technical team.
