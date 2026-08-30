"""PySide6 WebSocket client with no map or application-state knowledge."""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtNetwork import QAbstractSocket, QNetworkRequest
from PySide6.QtWebSockets import QWebSocket, QWebSocketProtocol

from integrations.adapters.base import IntegrationTransport
from integrations.contracts import validate_websocket_url


class WebSocketAdapter(IntegrationTransport):
    def __init__(self, url: str, access_token: str = "") -> None:
        super().__init__()
        self.url = validate_websocket_url(url)
        self._access_token = str(access_token)
        self._socket = QWebSocket()
        self._socket.connected.connect(self.opened)
        self._socket.disconnected.connect(self._on_disconnected)
        self._socket.textMessageReceived.connect(self.text_received)
        self._socket.errorOccurred.connect(self._on_error)

    def open(self) -> None:
        request = QNetworkRequest(QUrl(self.url))
        request.setRawHeader(b"User-Agent", b"The-Isle-Companion/experimental-api")
        if self._access_token:
            request.setRawHeader(
                b"Authorization",
                f"Bearer {self._access_token}".encode("utf-8"),
            )
        self._socket.open(request)

    def close(self) -> None:
        if self._socket.state() != QAbstractSocket.SocketState.UnconnectedState:
            self._socket.close(
                QWebSocketProtocol.CloseCode.CloseCodeNormal,
                "Companion disconnected",
            )

    def send_text(self, text: str) -> bool:
        if self._socket.state() != QAbstractSocket.SocketState.ConnectedState:
            return False
        return self._socket.sendTextMessage(text) == len(text.encode("utf-8"))

    def _on_disconnected(self) -> None:
        reason = self._socket.closeReason().strip() or "connection closed"
        self.closed.emit(reason)

    def _on_error(self, _error: QAbstractSocket.SocketError) -> None:
        self.failed.emit(self._socket.errorString())
