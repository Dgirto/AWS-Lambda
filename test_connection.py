"""Prueba de conexión estándar del conector aws_lambda.

Firma estándar Ruvic: def test_connection() -> tuple[bool, str]
- Lee la configuración EXCLUSIVAMENTE de las env vars RUVIC_AWS_LAMBDA_*.
- Nunca lanza excepciones; retorna (ok, mensaje).

Ejecutable también como script para pruebas locales:
    python test_connection.py
"""

from __future__ import annotations


def test_connection() -> tuple[bool, str]:
    """Verifica acceso a Lambda listando funciones, usando las env vars
    RUVIC_AWS_LAMBDA_*."""
    try:
        from ruvic_aws_lambda_connector import (
            LambdaAuthError,
            LambdaClient,
            LambdaDataError,
            LambdaNetworkError,
        )
    except ImportError:
        return (
            False,
            "La librería ruvic-aws-lambda-connector no está instalada. "
            "Instala con: pip install git+https://github.com/Dgirto/"
            "AWS-Lambda.git#subdirectory=lib",
        )

    try:
        client = LambdaClient()  # valida que existan las env vars
    except ValueError as exc:
        return False, str(exc)

    try:
        client.ping()
    except LambdaAuthError as exc:
        return False, f"Autenticación fallida: {exc}"
    except LambdaNetworkError as exc:
        return False, f"Error de red: {exc}"
    except LambdaDataError as exc:
        return False, f"Error de datos: {exc}"
    except Exception as exc:  # red de seguridad: jamás propagar
        return False, f"Error inesperado: {exc}"

    return (True, f"Conexión exitosa a AWS Lambda en {client.config.region}")


if __name__ == "__main__":
    ok, message = test_connection()
    print(f"{'OK' if ok else 'FALLO'}: {message}")
    raise SystemExit(0 if ok else 1)
