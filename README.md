# Conector AWS Lambda (CON-024)

Conector Ruvic para invocación de funciones AWS Lambda. Permite listar
funciones, invocar una función con un payload JSON (síncrona o
asíncrona) y revisar los logs recientes de CloudWatch para consultar el
resultado de invocaciones pasadas.

> **Este conector ejecuta código.** `invoke_function` dispara la
> ejecución real de la función Lambda, con todos sus efectos
> secundarios. No es de solo lectura.

## Instalación

```bash
pip install git+https://github.com/Dgirto/AWS-Lambda.git#subdirectory=lib
```

Python 3.10+. Dependencia única: `boto3>=1.34,<2.0`.

## Permisos requeridos en AWS

Crea un usuario IAM dedicado (no reutilizar credenciales root ni de otra
aplicación) con una policy restringida por prefijo de nombre de función:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["lambda:ListFunctions"],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": ["lambda:InvokeFunction"],
      "Resource": "arn:aws:lambda:*:*:function:ruvic-*"
    },
    {
      "Effect": "Allow",
      "Action": ["logs:DescribeLogStreams", "logs:GetLogEvents"],
      "Resource": "arn:aws:logs:*:*:log-group:/aws/lambda/ruvic-*:*"
    }
  ]
}
```

- `lambda:ListFunctions`: necesario para `lambda.list_functions` (esta
  acción no admite restricción por Resource, solo `"*"`).
- `lambda:InvokeFunction`: necesario para `lambda.invoke`. Restringe el
  Resource a un prefijo de nombres de función (ej. `ruvic-*`) para que el
  conector solo pueda ejecutar las funciones destinadas a Ruvic.
- `logs:DescribeLogStreams` y `logs:GetLogEvents`: necesarios para
  `lambda.get_logs`, restringidos al mismo prefijo de log groups.
- No se otorgan permisos de administración (`lambda:CreateFunction`,
  `lambda:DeleteFunction`, `lambda:UpdateFunctionCode`, etc.).

## Variables de entorno (`RUVIC_AWS_LAMBDA_*`)

| Variable | Obligatoria | Descripción |
|----------|-------------|-------------|
| `RUVIC_AWS_LAMBDA_ACCESS_KEY_ID` | Sí | Access Key ID de IAM |
| `RUVIC_AWS_LAMBDA_SECRET_ACCESS_KEY` | Sí | Secret Access Key |
| `RUVIC_AWS_LAMBDA_REGION` | Sí | Región de AWS (ej. `us-east-1`) |
| `RUVIC_AWS_LAMBDA_CONNECT_TIMEOUT` | No (default `10`) | Timeout de conexión en segundos |

## Pruebas locales

Con una función Lambda real ya desplegada (usa el runtime de ejemplo
"hello-world" de Python 3.12, o cualquier función propia que reciba JSON
y responda algo):

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ./lib

export RUVIC_AWS_LAMBDA_ACCESS_KEY_ID=tu-access-key
export RUVIC_AWS_LAMBDA_SECRET_ACCESS_KEY=tu-secret-key
export RUVIC_AWS_LAMBDA_REGION=us-east-1

python test_connection.py
python validate_local.py --function nombre-de-tu-funcion
```

Prueba también los casos de error (credenciales incorrectas, función
inexistente, payload inválido) y verifica que los mensajes sean claros.

## Notas de integración

- `invoke_function` con `invocation_type="RequestResponse"` (default) es
  síncrono: espera el resultado y lo retorna, junto con las últimas
  líneas de log de esa invocación específica (`LogType="Tail"` de AWS,
  limitado a 4 KB).
- `invocation_type="Event"` es fire-and-forget: AWS no retorna el
  resultado por esta vía. Usa `get_recent_logs` después para revisar qué
  pasó — es la única forma real de consultar el resultado de una
  invocación asíncrona, ya que Lambda no tiene una API de "obtener
  resultado por request id".
- `payload` en las respuestas se parsea como JSON automáticamente si es
  posible; si la función responde texto plano no JSON, viene como `str`.
- Reintentos: el cliente usa el modo `standard` de boto3 con 2 intentos
  máximo, para no ocultar errores reales ni re-ejecutar funciones con
  efectos secundarios por reintentos silenciosos excesivos.
