# Migraciones de Base de Datos

## Migración 001: Actualizar tamaño de payment_method

Esta migración actualiza el tamaño de la columna `payment_method` de `VARCHAR(50)` a `VARCHAR(200)` en las tablas `orders` y `sale_retry_queue` para soportar múltiples métodos de pago combinados (ej: "card,wallet").

### Opción 1: Ejecutar con script Python (Recomendado)

```bash
cd bausing-backend
python migrations/run_migration.py
```

Este script:
- Ejecuta la migración de forma segura
- Verifica que los cambios se aplicaron correctamente
- Muestra un resumen de las columnas actualizadas

### Opción 2: Ejecutar SQL directamente

Si prefieres ejecutar el SQL directamente con `psql`:

```bash
psql -d bausing -f migrations/001_update_payment_method_size.sql
```

O desde la línea de comandos de PostgreSQL:

```sql
\i migrations/001_update_payment_method_size.sql
```

### Verificar manualmente

Para verificar que los cambios se aplicaron:

```sql
SELECT 
    table_name,
    column_name,
    data_type,
    character_maximum_length
FROM information_schema.columns
WHERE table_name IN ('orders', 'sale_retry_queue')
  AND column_name = 'payment_method';
```

Deberías ver `character_maximum_length = 200` para ambas tablas.

### Notas

- Esta migración es **no destructiva**: solo cambia el tamaño máximo del campo, no afecta los datos existentes
- Los valores existentes seguirán funcionando normalmente
- No requiere hacer backup (aunque siempre es recomendable)
