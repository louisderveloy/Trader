# Grafana Dashboard Files (External Hosting)

## Overview

This directory contains Grafana dashboard JSON files and provisioning configurations for **reference and export only**. Grafana is now hosted on a separate external server for multi-project monitoring.

## Directory Structure

```
/grafana/
  /dashboards/          → Dashboard JSON files (import into external Grafana)
  /provisioning/
    /datasources/       → PostgreSQL datasource configuration (reference)
    /dashboards/        → Dashboard provisioning config (reference)
```

## Connecting External Grafana to PostgreSQL

Your external Grafana instance needs to connect to the PostgreSQL database hosted by this project.

### Connection Parameters

| Parameter | Value |
|---|---|
| **Type** | PostgreSQL |
| **Host** | `<server-ip>:5432` |
| **Database** | `${POSTGRES_DB}` (from .env, default: `trader_bot`) |
| **User** | `${POSTGRES_USER}` (from .env, default: `trader`) |
| **Password** | `${POSTGRES_PASSWORD}` (from .env) |
| **SSL Mode** | `prefer` (or `require` for production) |
| **Version** | PostgreSQL 16 with TimescaleDB 2.27.2 |

### Security Considerations

**Development:**
- PostgreSQL exposed on `localhost:5432`
- Safe for local development

**Production:**
- PostgreSQL exposed on `<server-ip>:5432`
- ⚠️ **CRITICAL**: Use firewall rules to restrict access to trusted IPs only
- Consider using PostgreSQL SSL certificates for encrypted connections
- Use strong passwords in production (change from .env.example defaults)

### Firewall Configuration Example (iptables)

```bash
# Allow PostgreSQL access only from Grafana server IP
sudo iptables -A INPUT -p tcp --dport 5432 -s <grafana-server-ip> -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 5432 -j DROP

# Make rules persistent
sudo iptables-save > /etc/iptables/rules.v4
```

## Importing Dashboards into External Grafana

### Method 1: Manual Import (Recommended)

1. **Create PostgreSQL datasource** in external Grafana:
   - Go to **Configuration > Data Sources > Add data source**
   - Select **PostgreSQL**
   - Enter connection parameters (see table above)
   - Set **Name**: `trader-bot-postgres` (or update JSON files to match your name)
   - Test connection and save

2. **Import dashboard JSON files**:
   - Go to **Dashboards > Import**
   - Upload JSON file from `/grafana/dashboards/`
   - Select the PostgreSQL datasource created in step 1
   - Click **Import**

3. **Repeat for all dashboards** in `/grafana/dashboards/`

### Method 2: Automated Provisioning (Advanced)

If your external Grafana supports provisioning:

1. Copy `/grafana/provisioning/datasources/` to your Grafana provisioning directory
2. Copy `/grafana/provisioning/dashboards/` to your Grafana provisioning directory
3. Update datasource configuration with correct connection parameters
4. Restart Grafana to apply provisioning

## Available Dashboards

### P&L Global
- Equity curve over time
- Maximum drawdown visualization
- Performance vs buy-and-hold BTC
- Cumulative returns

### Trades
- Filterable trades table
- P&L distribution histogram
- Win/loss ratio
- Heatmap by hour of day and day of week

### Run Detail
- Equity curve for specific `run_id`
- Indicator values over time
- Signals timeline
- Trade markers on price chart

### Comparaison Runs
- Overlay equity curves for multiple `run_id`
- Side-by-side metrics comparison
- Performance attribution

### Replay
- Time slider to replay a backtest
- Indicator values at each timestamp
- Decision logic visualization

### Optimisations Optuna
- Parallel coordinates plot for hyperparameters
- Parameter importance analysis
- Trial history and convergence

### Santé Bot
- API latency metrics
- Error rate and logs
- Rejected orders
- System health indicators

## Database Schema Reference

The PostgreSQL database uses the following key tables:

| Table | Description |
|---|---|
| `candles` | OHLCV data (TimescaleDB hypertable) |
| `trades` | Completed trades with P&L |
| `signals` | Strategy decisions with scores |
| `runs` | Backtest/optimization/live runs |
| `indicators_values` | Calculated indicator values |
| `weights_sets` | Optimized indicator weights |
| `optuna_studies` | Optimization study results |

See `/docs/A1_ERD.md` for complete schema documentation.

## Linking Dashboard to External Grafana

If you want the Vue.js dashboard to link to external Grafana:

1. Set `VITE_GRAFANA_BASE_URL` in `.env`:
   ```bash
   VITE_GRAFANA_BASE_URL=https://your-external-grafana.com
   ```

2. Rebuild dashboard container:
   ```bash
   docker compose up -d --build dashboard
   ```

3. Dashboard will now show "View in Grafana" links pointing to external instance

## Troubleshooting

### Cannot connect to PostgreSQL

**Issue**: Grafana shows "database connection failed"

**Solutions**:
- Verify PostgreSQL is running: `docker compose ps postgres`
- Check firewall allows connections from Grafana server IP
- Verify credentials match `.env` file
- Test connection with psql: `psql -h <server-ip> -U trader -d trader_bot`

### Dashboards show "No data"

**Issue**: Dashboards imported but show no data

**Solutions**:
- Verify datasource name matches JSON files (default: `trader-bot-postgres`)
- Check database has data: `docker compose exec postgres psql -U trader -d trader_bot -c "SELECT COUNT(*) FROM candles;"`
- Verify time range selector in Grafana (default: last 24 hours)
- Run historical data fetch: `docker compose exec bot python -m scripts.fetch_historical_data`

### Query performance is slow

**Issue**: Dashboard queries take >10 seconds

**Solutions**:
- Verify TimescaleDB hypertable is configured: `SELECT * FROM timescaledb_information.hypertables;`
- Check indexes exist: `\d candles` in psql
- Consider adding continuous aggregates for frequently-queried metrics
- Reduce time range in Grafana queries

## Support

For issues related to:
- **Grafana configuration**: Consult [Grafana documentation](https://grafana.com/docs/)
- **PostgreSQL connection**: Check PostgreSQL logs: `docker compose logs postgres`
- **Database schema**: See `/docs/A1_ERD.md`
- **Dashboard modifications**: Edit JSON files in `/grafana/dashboards/` and re-import

## Version History

- **2026-06-04**: Moved Grafana to external hosting, kept JSON files for reference
- **2026-06-03**: Initial dashboard creation with provisioning
