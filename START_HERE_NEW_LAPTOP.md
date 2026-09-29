# Sportland Smart × Shopify V1.1 — nueva laptop

Esta versión ya elimina el paso manual de generar y exportar `SHOPIFY_ADMIN_ACCESS_TOKEN`.
El matcher puede obtener su token por sí solo usando `SHOPIFY_CLIENT_ID` + `SHOPIFY_CLIENT_SECRET`.

## 1. Crear el entorno sin activar PowerShell scripts

Desde la carpeta del proyecto:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

No hace falta ejecutar `Activate.ps1`.

## 2. Crear configuración local

```powershell
Copy-Item .env.example .env
notepad .env
```

Completa solo:

```text
SHOPIFY_CLIENT_ID=...
SHOPIFY_CLIENT_SECRET=...
```

La tienda ya está configurada como:

```text
SHOPIFY_SHOP=sportland-sales.myshopify.com
```

No compartas `.env`, no lo subas a Git y no pegues el secret en chats.

## 3. Validar

```powershell
.\.venv\Scripts\python.exe validate_config.py
```

Debe mostrar:

```text
Configuration OK.
Shopify auth mode: client_credentials
Read-only V1.1 is ready to run.
```

## 4. Probar offline

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## 5. Ejecutar contra Shopify real

```powershell
.\.venv\Scripts\python.exe run_match.py
```

El programa ahora hace automáticamente:

1. lee Client ID + Client Secret;
2. solicita un access token a Shopify;
3. mantiene el token solo en memoria;
4. consulta productos/variantes/inventario;
5. compara demanda vs oferta;
6. escribe reportes CSV/JSON;
7. no modifica Shopify ni Smart.

## Estado Smart

Por ahora la entrada de Smart sigue siendo el CSV local:

```text
eventos_log.csv -> matcher <- Shopify API live
```

La siguiente integración será reemplazar el CSV por lectura directa de Google Sheets.
