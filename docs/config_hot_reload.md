# Configuration Hot Reload

## Overview

The trading bot now supports **hot configuration reload** using PostgreSQL LISTEN/NOTIFY. When the config table is updated, all running bot instances automatically reload their configuration without requiring a restart.

## How It Works

```
┌─────────────┐
│   Config    │  UPDATE config SET ...
│   Update    │
└──────┬──────┘
       │
       │ Trigger: on_config_updated
       ▼
┌─────────────────────────┐
│  PostgreSQL Trigger     │
│  notify_config_updated  │
└──────┬─────────┬────────┘
       │         │
       │ pg_notify('config_updated', ...)
       ▼         ▼
┌──────────┐  ┌──────────┐  ┌──────────┐
│  Paper   │  │  Live    │  │  Live    │
│  Bot     │  │  Testnet │  │  Mainnet │
└──────────┘  └──────────┘  └──────────┘
   │              │              │
   └──────────────┴──────────────┘
                  │
        All instances reload config
```

## Features

- ✅ **Zero Downtime**: Bots continue trading during config reload
- ✅ **Automatic**: No manual intervention required
- ✅ **Universal**: Works for all trading modes (paper, live testnet, live mainnet)
- ✅ **Safe**: Non-fatal if reload fails - bot continues with current config
- ✅ **Transparent**: Logs all config changes with old → new values

## Database Setup

The system uses a PostgreSQL trigger created by migration `008_add_config_notify_trigger.py`:

```sql
-- Trigger function
CREATE OR REPLACE FUNCTION notify_config_updated()
RETURNS trigger AS $$
BEGIN
    PERFORM pg_notify(
        'config_updated',
        json_build_object(
            'id', NEW.id::text,
            'config', NEW.config,
            'updated_at', NEW.updated_at::text
        )::text
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger on config table
CREATE TRIGGER on_config_updated
AFTER INSERT OR UPDATE ON config
FOR EACH ROW
EXECUTE FUNCTION notify_config_updated();
```

## Testing

### Option 1: Using the Test Script

1. Start a paper trading bot in one terminal:
   ```bash
   docker compose exec bot python -m main paper --symbol BTCUSDT
   ```

2. In another terminal, run the config update script:
   ```bash
   docker compose exec bot python /tmp/test_config_reload.py
   ```

3. Check the bot logs for the reload message:
   ```
   ============================================================
   CONFIG UPDATE NOTIFICATION RECEIVED
     Channel: config_updated
     From PID: 12345
     Config ID: 089e7d6b-445c-431c-94f1-35c197e41e97
     Updated at: 2026-06-08 20:30:00+00:00
   ============================================================
   Reloading configuration from database...
   Configuration changes detected:
     Entry threshold: 1.0 → 0.65
   ✓ Configuration reloaded successfully
   ============================================================
   ```

### Option 2: Direct Database Update

1. Start bot instance(s)

2. Update config directly in database:
   ```sql
   UPDATE config
   SET config = jsonb_set(
       config,
       '{strategy,entry_threshold}',
       '0.7'::jsonb
   ),
   updated_at = NOW()
   WHERE id = (SELECT id FROM config LIMIT 1);
   ```

3. All running instances will automatically reload

### Option 3: Via API (Future)

Once the config API endpoint is implemented:
```bash
curl -X PUT http://localhost:8000/api/config \
  -H "Content-Type: application/json" \
  -d '{"strategy": {"entry_threshold": 0.7}}'
```

## Configuration Changes Logged

The system logs the following changes when detected:
- Entry threshold
- Exit threshold
- Confirmation candles
- Max trades per day
- Position size mode
- Stop-loss settings
- Take-profit settings
- Risk management parameters

## Bot Behavior

When a config update notification is received:

1. **Notification Received**: Bot logs the notification details
2. **Config Reload**: Fetches latest config from database
3. **Change Detection**: Compares old vs new config
4. **Weights Reload**: Reloads active weights if changed
5. **Logging**: Logs all detected changes
6. **Resume**: Continues trading with new configuration

## Error Handling

- **Listener Fails to Start**: Non-fatal, bot continues with initial config
- **Notification Parse Error**: Logged, bot continues with current config
- **Config Reload Error**: Logged with warning, bot continues with previous config
- **Database Connection Lost**: Lock auto-released, listener reconnects on restart

## Implementation Details

### Key Methods (in `bot/scripts/trading.py`)

```python
class TradingBot:
    async def _start_config_listener(self):
        """Start listening for config updates"""

    async def _handle_config_notification(self, connection, pid, channel, payload):
        """Handle incoming config update notifications"""

    async def _reload_config(self):
        """Reload configuration from database (hot reload)"""

    async def _stop_config_listener(self):
        """Stop the config listener"""
```

### Lifecycle Integration

```python
async def start(self):
    # ... initialization ...
    await self._start_config_listener()  # Start listener
    await self._trading_loop()

async def stop(self):
    # ... cleanup ...
    await self._stop_config_listener()   # Stop listener
```

## Performance Impact

- **Minimal**: Listener uses a dedicated lightweight connection
- **No Polling**: Event-driven, only activates on actual config changes
- **Asynchronous**: Config reload happens in background, doesn't block trading

## Monitoring

### Check Active Listeners

```sql
SELECT pid, query_start, state, query
FROM pg_stat_activity
WHERE datname = 'trading_bot'
AND query LIKE '%LISTEN%';
```

### Check Notification History

All config updates are logged by the bot with timestamps and change details in the bot logs.

## Limitations

- Config changes requiring exchange reconnection (e.g., API keys) still need manual restart
- Weights changes are reloaded, but ongoing positions use their entry weights

## Future Enhancements

- Dashboard UI for config updates
- Config change history/audit log
- Rollback mechanism for bad configs
- Config validation before applying
- Discord notifications for config changes
