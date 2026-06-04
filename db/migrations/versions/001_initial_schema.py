"""initial_schema

Revision ID: 001
Revises:
Create Date: 2026-06-03 21:00:00.000000

Creates all tables for the trading bot:
- runs: Central table for all execution types
- candles: TimescaleDB hypertable for OHLCV data
- indicators_values: Calculated indicator values per run
- user_indicator: Manual user indicator with expiration
- signals: Bot decisions with weighted scores
- orders: Exchange orders tracking
- trades: Completed trades with P&L
- weights_sets: Optimized or manual weight sets
- optuna_studies: Optimization study results
- users: User accounts (mono-user v1, multi-user ready)
- notifications_log: Discord notification history
- errors_log: Error tracking
- daily_pnl: Continuous aggregate for daily P&L (TimescaleDB)
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==========================================
    # Table: runs
    # ==========================================
    op.create_table(
        'runs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('run_type', sa.String(20), nullable=False, comment='backtest, optimization, paper, live'),
        sa.Column('status', sa.String(20), nullable=False, comment='running, completed, failed, stopped'),
        sa.Column('started_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('completed_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('config_snapshot', JSONB, nullable=False, comment='Complete configuration snapshot'),
        sa.Column('metadata', JSONB, nullable=True, comment='Additional metadata'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()'))
    )
    op.create_index('idx_runs_type_status', 'runs', ['run_type', 'status'])
    op.create_index('idx_runs_started_at', 'runs', [sa.text('started_at DESC')])

    # ==========================================
    # Table: candles (TimescaleDB hypertable)
    # ==========================================
    op.create_table(
        'candles',
        sa.Column('time', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('timeframe', sa.String(10), nullable=False),
        sa.Column('open', sa.DECIMAL(20, 8), nullable=False),
        sa.Column('high', sa.DECIMAL(20, 8), nullable=False),
        sa.Column('low', sa.DECIMAL(20, 8), nullable=False),
        sa.Column('close', sa.DECIMAL(20, 8), nullable=False),
        sa.Column('volume', sa.DECIMAL(20, 8), nullable=False),
        sa.PrimaryKeyConstraint('time', 'symbol', 'timeframe')
    )

    # Convert to TimescaleDB hypertable
    op.execute("SELECT create_hypertable('candles', 'time');")

    op.create_index('idx_candles_symbol_timeframe', 'candles', ['symbol', 'timeframe', sa.text('time DESC')])

    # ==========================================
    # Table: indicators_values
    # ==========================================
    op.create_table(
        'indicators_values',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('run_id', UUID(as_uuid=True), nullable=False),
        sa.Column('time', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('indicator_name', sa.String(50), nullable=False),
        sa.Column('values', JSONB, nullable=False, comment='Raw indicator values'),
        sa.Column('signal', sa.DECIMAL(5, 4), nullable=False, comment='Normalized signal [-1, 1]'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['run_id'], ['runs.id'], name='fk_indicators_values_run_id')
    )
    op.create_index('idx_indicators_run_time', 'indicators_values', ['run_id', 'time'])
    op.create_index('idx_indicators_symbol_name', 'indicators_values', ['symbol', 'indicator_name', sa.text('time DESC')])

    # ==========================================
    # Table: user_indicator
    # ==========================================
    op.create_table(
        'user_indicator',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('signal', sa.DECIMAL(5, 4), nullable=False, comment='Slider value [-1, 1]'),
        sa.Column('note', sa.Text, nullable=True),
        sa.Column('expires_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()'))
    )
    op.create_index('idx_user_indicator_symbol', 'user_indicator', ['symbol'])
    op.create_index('idx_user_indicator_expires', 'user_indicator', ['expires_at'])

    # ==========================================
    # Table: signals
    # ==========================================
    op.create_table(
        'signals',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('run_id', UUID(as_uuid=True), nullable=False),
        sa.Column('time', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('signal_type', sa.String(10), nullable=False, comment='entry_long, exit, skip'),
        sa.Column('weighted_score', sa.DECIMAL(5, 4), nullable=False, comment='Weighted score [-1, 1]'),
        sa.Column('weights_snapshot', JSONB, nullable=False, comment='Snapshot of active weights'),
        sa.Column('indicators_snapshot', JSONB, nullable=False, comment='All indicator values'),
        sa.Column('decision_reason', sa.Text, nullable=True, comment='Reason for decision or skip'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['run_id'], ['runs.id'], name='fk_signals_run_id')
    )
    op.create_index('idx_signals_run_time', 'signals', ['run_id', 'time'])
    op.create_index('idx_signals_type', 'signals', ['signal_type'])

    # ==========================================
    # Table: orders
    # ==========================================
    op.create_table(
        'orders',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('run_id', UUID(as_uuid=True), nullable=False),
        sa.Column('signal_id', UUID(as_uuid=True), nullable=True),
        sa.Column('exchange_order_id', sa.String(100), nullable=True),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('side', sa.String(10), nullable=False, comment='buy, sell'),
        sa.Column('order_type', sa.String(20), nullable=False, comment='limit, market'),
        sa.Column('status', sa.String(20), nullable=False, comment='pending, filled, cancelled, rejected'),
        sa.Column('quantity', sa.DECIMAL(20, 8), nullable=False),
        sa.Column('price', sa.DECIMAL(20, 8), nullable=True),
        sa.Column('filled_quantity', sa.DECIMAL(20, 8), server_default=sa.text('0')),
        sa.Column('filled_price', sa.DECIMAL(20, 8), nullable=True),
        sa.Column('commission', sa.DECIMAL(20, 8), nullable=True),
        sa.Column('placed_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('filled_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('cancelled_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('metadata', JSONB, nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['run_id'], ['runs.id'], name='fk_orders_run_id'),
        sa.ForeignKeyConstraint(['signal_id'], ['signals.id'], name='fk_orders_signal_id')
    )
    op.create_index('idx_orders_run', 'orders', ['run_id'])
    op.create_index('idx_orders_status', 'orders', ['status'])
    op.create_index('idx_orders_exchange_id', 'orders', ['exchange_order_id'])

    # ==========================================
    # Table: trades
    # ==========================================
    op.create_table(
        'trades',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('run_id', UUID(as_uuid=True), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('entry_order_id', UUID(as_uuid=True), nullable=True),
        sa.Column('exit_order_id', UUID(as_uuid=True), nullable=True),
        sa.Column('side', sa.String(10), nullable=False, comment='long, short'),
        sa.Column('entry_price', sa.DECIMAL(20, 8), nullable=False),
        sa.Column('exit_price', sa.DECIMAL(20, 8), nullable=False),
        sa.Column('quantity', sa.DECIMAL(20, 8), nullable=False),
        sa.Column('pnl', sa.DECIMAL(20, 8), nullable=False, comment='Profit & Loss in USDT'),
        sa.Column('pnl_percent', sa.DECIMAL(10, 4), nullable=False, comment='P&L in percentage'),
        sa.Column('commission_total', sa.DECIMAL(20, 8), nullable=False),
        sa.Column('opened_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('closed_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('duration_seconds', sa.Integer, nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['run_id'], ['runs.id'], name='fk_trades_run_id'),
        sa.ForeignKeyConstraint(['entry_order_id'], ['orders.id'], name='fk_trades_entry_order_id'),
        sa.ForeignKeyConstraint(['exit_order_id'], ['orders.id'], name='fk_trades_exit_order_id')
    )
    op.create_index('idx_trades_run', 'trades', ['run_id'])
    op.create_index('idx_trades_closed_at', 'trades', [sa.text('closed_at DESC')])
    op.create_index('idx_trades_pnl', 'trades', [sa.text('pnl DESC')])

    # ==========================================
    # Table: weights_sets
    # ==========================================
    op.create_table(
        'weights_sets',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('source', sa.String(20), nullable=False, comment='optuna, manual'),
        sa.Column('weights', JSONB, nullable=False, comment='{"ema": 0.15, "macd": 0.20, ...}'),
        sa.Column('optimization_score', sa.DECIMAL(10, 4), nullable=True, comment='Sharpe or other metric'),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default=sa.text('FALSE')),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()'))
    )
    op.create_index('idx_weights_active', 'weights_sets', ['is_active'])

    # ==========================================
    # Table: optuna_studies
    # ==========================================
    op.create_table(
        'optuna_studies',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('study_name', sa.String(100), nullable=False),
        sa.Column('run_id', UUID(as_uuid=True), nullable=True),
        sa.Column('n_trials', sa.Integer, nullable=False),
        sa.Column('best_value', sa.DECIMAL(10, 4), nullable=True),
        sa.Column('best_params', JSONB, nullable=True),
        sa.Column('weights_set_id', UUID(as_uuid=True), nullable=True),
        sa.Column('started_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('completed_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('metadata', JSONB, nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['run_id'], ['runs.id'], name='fk_optuna_studies_run_id'),
        sa.ForeignKeyConstraint(['weights_set_id'], ['weights_sets.id'], name='fk_optuna_studies_weights_set_id')
    )
    op.create_index('idx_optuna_study_name', 'optuna_studies', ['study_name'])

    # ==========================================
    # Table: users
    # ==========================================
    op.create_table(
        'users',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('username', sa.String(50), nullable=False, unique=True),
        sa.Column('email', sa.String(100), nullable=False, unique=True),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default=sa.text('TRUE')),
        sa.Column('is_admin', sa.Boolean, nullable=False, server_default=sa.text('FALSE')),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()'))
    )
    op.create_index('idx_users_username', 'users', ['username'])
    op.create_index('idx_users_email', 'users', ['email'])

    # ==========================================
    # Table: notifications_log
    # ==========================================
    op.create_table(
        'notifications_log',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('notification_type', sa.String(50), nullable=False),
        sa.Column('message', sa.Text, nullable=False),
        sa.Column('sent_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('status', sa.String(20), nullable=False, comment='sent, failed'),
        sa.Column('metadata', JSONB, nullable=True)
    )
    op.create_index('idx_notifications_sent_at', 'notifications_log', [sa.text('sent_at DESC')])
    op.create_index('idx_notifications_type', 'notifications_log', ['notification_type'])

    # ==========================================
    # Table: errors_log
    # ==========================================
    op.create_table(
        'errors_log',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('run_id', UUID(as_uuid=True), nullable=True),
        sa.Column('error_type', sa.String(100), nullable=False),
        sa.Column('message', sa.Text, nullable=False),
        sa.Column('stack_trace', sa.Text, nullable=True),
        sa.Column('occurred_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('metadata', JSONB, nullable=True),
        sa.ForeignKeyConstraint(['run_id'], ['runs.id'], name='fk_errors_log_run_id')
    )
    op.create_index('idx_errors_run', 'errors_log', ['run_id'])
    op.create_index('idx_errors_occurred_at', 'errors_log', [sa.text('occurred_at DESC')])

    # ==========================================
    # NOTE: Continuous Aggregate (daily_pnl)
    # ==========================================
    # Continuous aggregates will be added in Phase 7 as a separate migration
    # because they cannot run inside a transaction block.
    # See: db/migrations/versions/002_continuous_aggregates.py (to be created in Phase 7)


def downgrade() -> None:
    # Drop tables in reverse order (respecting foreign keys)
    op.drop_table('errors_log')
    op.drop_table('notifications_log')
    op.drop_table('users')
    op.drop_table('optuna_studies')
    op.drop_table('weights_sets')
    op.drop_table('trades')
    op.drop_table('orders')
    op.drop_table('signals')
    op.drop_table('user_indicator')
    op.drop_table('indicators_values')
    op.drop_table('candles')
    op.drop_table('runs')
