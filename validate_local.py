"""Validación local del conector aws_lambda: ejercita las 3 capacidades.

Uso:
    python validate_local.py --function NOMBRE_DE_TU_FUNCION

Requiere las variables RUVIC_AWS_LAMBDA_* exportadas en el entorno, y una
función Lambda real ya desplegada (puede ser cualquiera de prueba que
reciba un evento JSON y responda algo, ej. la función de ejemplo
"hello-world" del runtime python3.12 de AWS).
"""

import argparse

from ruvic_aws_lambda_connector import LambdaClient, setup_logging

parser = argparse.ArgumentParser()
parser.add_argument("--function", required=True, help="Nombre de la función Lambda a invocar")
args = parser.parse_args()

setup_logging("INFO")
client = LambdaClient()

print("== 1. Listar funciones ==")
functions = client.list_functions(limit=20)
for fn in functions:
    print(f"  {fn['name']} ({fn['runtime']})")
assert any(f["name"] == args.function for f in functions), f"{args.function!r} no aparece en list_functions"

print(f"== 2. Invocar '{args.function}' con payload de prueba ==")
result = client.invoke_function(args.function, {"ruvic_test": True})
print(f"  status_code={result['status_code']} function_error={result['function_error']}")
print(f"  payload={result['payload']}")
assert result["status_code"] == 200, "La invocación no retornó status 200"

print(f"== 3. Revisar logs recientes de '{args.function}' ==")
logs = client.get_recent_logs(args.function, limit=10)
for entry in logs:
    print(f"  {entry['message']}")
assert logs, "No se obtuvieron logs recientes"

print("\nTodo OK: list_functions, invoke_function y get_recent_logs funcionan.")
