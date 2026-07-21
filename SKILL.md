---
name: aws-lambda
description: >
  Usa la librería ruvic_aws_lambda_connector para invocar funciones AWS
  Lambda - listar las funciones disponibles (list_functions), invocar una
  función con un payload JSON y recibir su resultado de inmediato
  (invoke_function), y revisar los logs recientes de una función en
  CloudWatch Logs (get_recent_logs), útil para inspeccionar el resultado
  de invocaciones asíncronas. Úsala cuando el usuario pida ejecutar,
  invocar o disparar una función Lambda, o revisar qué pasó en su última
  ejecución.
triggers:
- lambda
- aws lambda
- función serverless
- invocar función
---

# Conector AWS Lambda (ruvic_aws_lambda_connector)

Librería Python para invocar funciones AWS Lambda. Está **preinstalada en el runtime** cuando el conector está configurado (si no, instálala con `pip install git+https://github.com/Dgirto/AWS-Lambda.git#subdirectory=lib`).

## Regla crítica de credenciales

El código generado **NUNCA hardcodea credenciales**. Siempre se leen de variables de entorno, disponibles cuando el conector `aws_lambda` está configurado:

| Variable | Contenido |
|----------|-----------|
| `RUVIC_AWS_LAMBDA_ACCESS_KEY_ID` | Access Key ID de IAM |
| `RUVIC_AWS_LAMBDA_SECRET_ACCESS_KEY` | Secret Access Key |
| `RUVIC_AWS_LAMBDA_REGION` | Región de AWS (ej. `us-east-1`) |
| `RUVIC_AWS_LAMBDA_CONNECT_TIMEOUT` | (opcional) timeout en segundos |

Si estas variables NO existen, el conector no está configurado: no generes código que lo use; indica al usuario que lo configure en **Settings → Conectores**.

## Este conector ejecuta código (invoke)

`invoke_function` dispara la ejecución real de una función Lambda, con sus efectos secundarios (escrituras en base de datos, envío de correos, etc. — lo que sea que la función haga). No es una operación de solo lectura.

## Conexión (siempre igual)

```python
from ruvic_aws_lambda_connector import LambdaClient

client = LambdaClient()  # lee RUVIC_AWS_LAMBDA_* del entorno automáticamente
```

## Capacidad 1 — Listar funciones

```python
functions = client.list_functions(limit=50)
for fn in functions:
    print(f"{fn['name']} ({fn['runtime']}): {fn['description']}")
```

## Capacidad 2 — Invocar una función

```python
# Síncrono (default): espera el resultado
result = client.invoke_function("procesar-pedido", {"pedido_id": 123})
print(result["status_code"], result["payload"], result["function_error"])

# Asíncrono: dispara y no espera (para tareas largas)
client.invoke_function("enviar-reporte", {"mes": "2026-07"}, invocation_type="Event")
```

En modo `"RequestResponse"` (default), `payload` trae la respuesta real de la función (parseada como JSON si es posible) y `function_error` indica si la función lanzó una excepción. En modo `"Event"`, la invocación es de disparar-y-olvidar: `payload` viene `None` — usa `get_recent_logs` después para ver qué pasó.

## Capacidad 3 — Revisar el resultado en los logs

```python
logs = client.get_recent_logs("procesar-pedido", limit=50)
for entry in logs:
    print(entry["message"])
```

AWS no expone una API para consultar el resultado de una invocación Lambda por request id — los logs de CloudWatch son la forma real de revisar qué pasó, especialmente para invocaciones asíncronas (`invocation_type="Event"`).

## Manejo de errores

```python
from ruvic_aws_lambda_connector import (
    LambdaAuthError, LambdaDataError, LambdaNetworkError,
)

try:
    result = client.invoke_function("mi-funcion", {})
except LambdaAuthError:
    print("Credenciales inválidas o sin permiso IAM sobre esa función")
except LambdaNetworkError:
    print("No se pudo alcanzar Lambda — revisa la región y el acceso de red")
except LambdaDataError as e:
    print(f"Error de datos: {e}")  # ej. la función no existe
```

## Buenas prácticas al generar código

1. Lee credenciales SOLO de las variables `RUVIC_AWS_LAMBDA_*` (el constructor de `LambdaClient` ya lo hace).
2. Nunca imprimas `RUVIC_AWS_LAMBDA_SECRET_ACCESS_KEY` en logs ni en la salida.
3. Antes de invocar una función con efectos secundarios importantes, confirma con el usuario el nombre exacto de la función (usa `list_functions` para verificar que existe).
4. Revisa siempre `function_error` en la respuesta de `invoke_function` — un `status_code` 200 no garantiza que la función haya terminado sin errores internos.
5. Para tareas largas o que no necesitan respuesta inmediata, usa `invocation_type="Event"` en vez de esperar sincrónicamente.
