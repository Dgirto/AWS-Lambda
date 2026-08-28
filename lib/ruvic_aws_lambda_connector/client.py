"""Cliente de invocación de funciones AWS Lambda.

Capacidades:
- list_functions():    listar las funciones Lambda de la región configurada.
- invoke_function():   invocar una función con un payload JSON.
- get_recent_logs():   consultar los logs recientes de una función (la forma
                        real de revisar el resultado de invocaciones, en
                        especial las asíncronas — AWS no expone un "get
                        result by request id" para Lambda).

Las credenciales SIEMPRE provienen de variables de entorno
RUVIC_AWS_LAMBDA_* (ver config.LambdaConfig.from_env). Prohibido
hardcodearlas.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    EndpointConnectionError,
)

from .config import LambdaConfig
from .exceptions import (
    LambdaAuthError,
    LambdaConnectorError,
    LambdaDataError,
    LambdaNetworkError,
)
from .logging_utils import get_logger

_AUTH_ERROR_CODES = {
    "AccessDeniedException",
    "UnrecognizedClientException",
    "InvalidClientTokenId",
    "InvalidSignatureException",
}
_NOT_FOUND_ERROR_CODES = {"ResourceNotFoundException"}
_MAX_LIST_LIMIT = 200
_MAX_LOG_LIMIT = 500


def _validate_function_name(name: str) -> str:
    if name is not None and not isinstance(name, str):
        raise LambdaDataError(f"function_name debe ser un string, no {type(name).__name__}.")
    name = (name or "").strip()
    if not name:
        raise LambdaDataError("function_name no puede estar vacío.")
    return name


def _validate_limit(limit: Any, max_limit: int) -> int:
    try:
        return max(1, min(int(limit), max_limit))
    except (TypeError, ValueError) as exc:
        raise LambdaDataError(f"limit inválido: {limit!r}. Debe ser un número entero.") from exc


def _wrap_client_error(exc: ClientError, not_found_message: str) -> LambdaConnectorError:
    """Traduce un error de la API de AWS a una excepción propia, sin dejar
    escapar nunca el tipo crudo del SDK."""
    code = exc.response.get("Error", {}).get("Code", "")
    if code in _AUTH_ERROR_CODES:
        return LambdaAuthError(
            "Credenciales inválidas o sin permiso IAM suficiente para esta "
            "operación. Revisa la policy adjunta al usuario o rol."
        )
    if code in _NOT_FOUND_ERROR_CODES:
        return LambdaDataError(not_found_message)
    if code == "InvalidParameterValueException":
        return LambdaDataError(f"Parámetro inválido: {exc}")
    return LambdaDataError(f"Error de datos ({code}): {exc}")


class LambdaClient:
    """Cliente para listar, invocar y revisar los logs de funciones AWS
    Lambda en la región configurada.

    Args:
        config: configuración de conexión. Si se omite, se lee de las
            variables de entorno RUVIC_AWS_LAMBDA_* (comportamiento
            estándar en el runtime de la plataforma).

    Ejemplo:
        >>> client = LambdaClient()         # lee RUVIC_AWS_LAMBDA_* del entorno
        >>> client.invoke_function("procesar-pedido", {"pedido_id": 123})
        {'status_code': 200, 'payload': {'ok': True}, 'function_error': None, 'logs': '...'}
    """

    def __init__(self, config: LambdaConfig | None = None) -> None:
        self.config = config or LambdaConfig.from_env()
        self._logger = get_logger()
        self._lambda_client: Any = None
        self._logs_client: Any = None

    # ------------------------------------------------------------------ #
    # Conexión
    # ------------------------------------------------------------------ #

    def _boto_config(self) -> BotoConfig:
        return BotoConfig(
            connect_timeout=self.config.connect_timeout,
            read_timeout=max(self.config.connect_timeout, 60),
            retries={"max_attempts": 2, "mode": "standard"},
        )

    def _get_lambda_client(self) -> Any:
        if self._lambda_client is not None:
            return self._lambda_client
        self._lambda_client = boto3.client(
            "lambda",
            aws_access_key_id=self.config.access_key_id,
            aws_secret_access_key=self.config.secret_access_key,
            region_name=self.config.region,
            config=self._boto_config(),
        )
        return self._lambda_client

    def _get_logs_client(self) -> Any:
        if self._logs_client is not None:
            return self._logs_client
        self._logs_client = boto3.client(
            "logs",
            aws_access_key_id=self.config.access_key_id,
            aws_secret_access_key=self.config.secret_access_key,
            region_name=self.config.region,
            config=self._boto_config(),
        )
        return self._logs_client

    def ping(self) -> bool:
        """Verifica la conexión listando hasta 1 función.

        Returns:
            True si la conexión funciona.

        Raises:
            LambdaAuthError / LambdaNetworkError / LambdaDataError según el fallo.
        """
        try:
            self._get_lambda_client().list_functions(MaxItems=1)
        except ClientError as exc:
            raise _wrap_client_error(exc, "No se pudo listar funciones.") from exc
        except (EndpointConnectionError, BotoCoreError) as exc:
            raise LambdaNetworkError(
                f"No se pudo conectar al servicio Lambda en la región "
                f"{self.config.region!r} (timeout {self.config.connect_timeout}s). "
                "Verifica la región y el acceso de red."
            ) from exc
        self._logger.info("Ping exitoso a Lambda en %s", self.config.region)
        return True

    # ------------------------------------------------------------------ #
    # Capacidad 1: listar funciones
    # ------------------------------------------------------------------ #

    def list_functions(self, limit: int = 50) -> list[dict[str, Any]]:
        """Lista las funciones Lambda de la región configurada.

        Args:
            limit: máximo de funciones a retornar (default 50, máximo 200).

        Returns:
            Lista de dicts: {"name", "arn", "runtime", "last_modified", "description"}.

        Ejemplo:
            >>> client.list_functions()
            [{'name': 'procesar-pedido', 'arn': 'arn:aws:lambda:...', 'runtime': 'python3.12', ...}]
        """
        limit = _validate_limit(limit, _MAX_LIST_LIMIT)
        client = self._get_lambda_client()
        try:
            response = client.list_functions(MaxItems=limit)
        except ClientError as exc:
            raise _wrap_client_error(exc, "No se pudieron listar las funciones.") from exc
        except (EndpointConnectionError, BotoCoreError) as exc:
            raise LambdaNetworkError(f"No se pudo listar funciones: {exc}") from exc

        result = [
            {
                "name": fn["FunctionName"],
                "arn": fn["FunctionArn"],
                "runtime": fn.get("Runtime"),
                "last_modified": fn.get("LastModified"),
                "description": fn.get("Description", ""),
            }
            for fn in response.get("Functions", [])
        ]
        self._logger.info("Se listaron %d funciones", len(result))
        return result

    # ------------------------------------------------------------------ #
    # Capacidad 2: invocar una función
    # ------------------------------------------------------------------ #

    def invoke_function(
        self,
        function_name: str,
        payload: dict[str, Any] | None = None,
        invocation_type: str = "RequestResponse",
    ) -> dict[str, Any]:
        """Invoca una función Lambda con un payload JSON.

        Args:
            function_name: nombre (o ARN) de la función.
            payload: dict que se envía como evento de entrada (se serializa
                a JSON). None equivale a `{}`.
            invocation_type: "RequestResponse" (default, síncrono: espera y
                retorna el resultado) o "Event" (asíncrono: dispara la
                invocación y retorna de inmediato, sin resultado — usa
                get_recent_logs() después para revisar qué pasó).

        Returns:
            Dict con: status_code, payload (respuesta de la función, parseada
            como JSON si es posible; None en invocaciones "Event"),
            function_error (mensaje si la función lanzó una excepción, o
            None), logs (últimas líneas de CloudWatch Logs de esta
            invocación, solo disponibles en modo síncrono).

        Ejemplo:
            >>> client.invoke_function("procesar-pedido", {"pedido_id": 123})
            {'status_code': 200, 'payload': {'ok': True}, 'function_error': None, 'logs': '...'}
        """
        function_name = _validate_function_name(function_name)
        if invocation_type not in ("RequestResponse", "Event"):
            raise LambdaDataError(
                "invocation_type debe ser 'RequestResponse' o 'Event'."
            )
        try:
            payload_bytes = json.dumps(payload or {}).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise LambdaDataError(f"payload no es serializable a JSON: {exc}") from exc
        client = self._get_lambda_client()
        kwargs: dict[str, Any] = {
            "FunctionName": function_name,
            "InvocationType": invocation_type,
            "Payload": payload_bytes,
        }
        if invocation_type == "RequestResponse":
            kwargs["LogType"] = "Tail"
        try:
            response = client.invoke(**kwargs)
        except ClientError as exc:
            raise _wrap_client_error(
                exc, f"La función {function_name!r} no existe."
            ) from exc
        except (EndpointConnectionError, BotoCoreError) as exc:
            raise LambdaNetworkError(f"No se pudo invocar la función: {exc}") from exc

        raw_payload = response["Payload"].read()
        parsed_payload: Any = None
        if raw_payload:
            try:
                parsed_payload = json.loads(raw_payload)
            except (json.JSONDecodeError, UnicodeDecodeError):
                parsed_payload = raw_payload.decode("utf-8", errors="replace")

        logs = None
        if response.get("LogResult"):
            logs = base64.b64decode(response["LogResult"]).decode("utf-8", errors="replace")

        self._logger.info(
            'Invocada función "%s" (type=%s, status=%s, error=%s)',
            function_name, invocation_type, response.get("StatusCode"),
            response.get("FunctionError"),
        )
        return {
            "status_code": response.get("StatusCode"),
            "payload": parsed_payload,
            "function_error": response.get("FunctionError"),
            "logs": logs,
        }

    # ------------------------------------------------------------------ #
    # Capacidad 3: revisar logs recientes (consultar resultado)
    # ------------------------------------------------------------------ #

    def get_recent_logs(self, function_name: str, limit: int = 50) -> list[dict[str, Any]]:
        """Consulta las entradas más recientes de CloudWatch Logs de una
        función, en el stream de log más reciente.

        Es la forma real de revisar qué pasó en invocaciones pasadas,
        especialmente las asíncronas (invocation_type="Event"), ya que AWS
        no expone una API para consultar el resultado de una invocación
        Lambda por request id.

        Args:
            function_name: nombre de la función.
            limit: máximo de líneas de log a retornar (default 50, máximo 500).

        Returns:
            Lista de dicts: {"timestamp", "message"}, ordenados del más
            antiguo al más reciente.

        Ejemplo:
            >>> client.get_recent_logs("procesar-pedido", limit=20)
            [{'timestamp': '2026-07-17T10:00:00Z', 'message': 'START RequestId: ...'}]
        """
        function_name = _validate_function_name(function_name)
        limit = _validate_limit(limit, _MAX_LOG_LIMIT)
        log_group = f"/aws/lambda/{function_name}"
        logs_client = self._get_logs_client()
        try:
            streams = logs_client.describe_log_streams(
                logGroupName=log_group,
                orderBy="LastEventTime",
                descending=True,
                limit=1,
            )
            stream_names = [s["logStreamName"] for s in streams.get("logStreams", [])]
            if not stream_names:
                return []
            events = logs_client.get_log_events(
                logGroupName=log_group,
                logStreamName=stream_names[0],
                limit=limit,
                startFromHead=False,
            )
        except ClientError as exc:
            raise _wrap_client_error(
                exc,
                f"No hay logs para la función {function_name!r} (aún no se ha "
                "invocado, o el log group no existe).",
            ) from exc
        except (EndpointConnectionError, BotoCoreError) as exc:
            raise LambdaNetworkError(f"No se pudieron obtener los logs: {exc}") from exc

        result = [
            {
                "timestamp": event["timestamp"],
                "message": event["message"].rstrip("\n"),
            }
            for event in events.get("events", [])
        ]
        self._logger.info(
            'Obtenidas %d líneas de log de "%s"', len(result), function_name
        )
        return result
