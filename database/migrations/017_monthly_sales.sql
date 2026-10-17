-- Ventas totales por mes (v7.5): historial de la pestaña "Ventas" de la hoja de finanzas
-- (efectivo + tarjeta + plataformas) y los meses nuevos capturados en el portal.
-- Es la base de la estacionalidad: comparar contra el mismo mes de años anteriores.

CREATE TABLE IF NOT EXISTS finance_monthly_sales (
    sales_id BIGSERIAL PRIMARY KEY,
    year INT NOT NULL CHECK (year BETWEEN 2000 AND 2100),
    month INT NOT NULL CHECK (month BETWEEN 1 AND 12),
    cash_mxn NUMERIC(14,2) CHECK (cash_mxn >= 0),
    card_mxn NUMERIC(14,2) CHECK (card_mxn >= 0),
    platforms_mxn NUMERIC(14,2) CHECK (platforms_mxn >= 0),
    total_mxn NUMERIC(14,2) NOT NULL CHECK (total_mxn >= 0),
    source TEXT NOT NULL DEFAULT 'portal' CHECK (source IN ('hoja_ventas', 'portal')),
    updated_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (year, month)
);
