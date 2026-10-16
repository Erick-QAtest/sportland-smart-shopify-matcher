-- Finanzas capturadas en el portal (v7.3). Sustituyen las pestañas Deudas, Próximos pagos
-- y Caja externa de la hoja de finanzas. El pipeline las convierte al mismo formato que la
-- hoja y usa los parsers v2 existentes, así los cálculos no cambian.

CREATE TABLE IF NOT EXISTS finance_debts (
    debt_id BIGSERIAL PRIMARY KEY,
    creditor TEXT NOT NULL,
    balance_mxn NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (balance_mxn >= 0),
    status TEXT NOT NULL DEFAULT 'activa' CHECK (status IN ('activa', 'liquidada')),
    notes TEXT,
    source_row JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS finance_scheduled_payments (
    payment_id BIGSERIAL PRIMARY KEY,
    due_date DATE NOT NULL,
    concept TEXT NOT NULL DEFAULT '',
    creditor TEXT NOT NULL,
    amount_mxn NUMERIC(14,2) NOT NULL CHECK (amount_mxn > 0),
    status TEXT NOT NULL DEFAULT 'pendiente'
        CHECK (status IN ('pendiente', 'por confirmar', 'pagado', 'cancelado')),
    account_ref TEXT,
    category TEXT,
    notes TEXT,
    source_row JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_finance_scheduled_payments_due
    ON finance_scheduled_payments(due_date, status);

CREATE TABLE IF NOT EXISTS finance_cash_balances (
    account_id BIGSERIAL PRIMARY KEY,
    account_name TEXT NOT NULL,
    -- Texto libre como en la hoja; el parser cuenta como efectivo si contiene "efectivo".
    account_type TEXT NOT NULL DEFAULT 'Cuenta',
    balance_mxn NUMERIC(14,2) NOT NULL DEFAULT 0,
    available BOOLEAN NOT NULL DEFAULT true,
    cut_date DATE NOT NULL DEFAULT current_date,
    notes TEXT,
    source_row JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Bitácora de cambios hechos desde el portal o la importación.
CREATE TABLE IF NOT EXISTS finance_change_log (
    change_id BIGSERIAL PRIMARY KEY,
    table_name TEXT NOT NULL,
    record_id BIGINT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('insert', 'update', 'import')),
    before_data JSONB,
    after_data JSONB,
    actor TEXT,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_finance_change_log_record
    ON finance_change_log(table_name, record_id, changed_at DESC);
