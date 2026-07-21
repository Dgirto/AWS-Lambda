"""Excepciones propias del conector AWS Lambda.

Separan los tres tipos de fallo que el usuario debe distinguir:
autenticación, red/servidor y datos. Nunca exponemos excepciones
crípticas del SDK subyacente.
"""


class LambdaConnectorError(Exception):
    """Error base del conector."""


class LambdaAuthError(LambdaConnectorError):
    """Credenciales inválidas o permisos IAM insuficientes."""


class LambdaNetworkError(LambdaConnectorError):
    """No se pudo alcanzar el servicio (red, timeout, error temporal de AWS)."""


class LambdaDataError(LambdaConnectorError):
    """La operación es válida pero la función/payload es inválido."""
