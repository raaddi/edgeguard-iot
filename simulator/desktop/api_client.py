"""Bounded, cancellable HTTP reads on Qt's event loop; no GUI-blocking requests."""

import json
from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkProxy, QNetworkReply, QNetworkRequest


class ApiClient(QObject):
    result = Signal(str, object, str)
    MAX_BYTES = 8 * 1024 * 1024

    def __init__(self, parent=None, timeout_ms=5000):
        super().__init__(parent)
        self.manager = QNetworkAccessManager(self)
        self.manager.setProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))
        self.reply = None
        self.generation = 0
        self.timeout_ms = timeout_ms

    def cancel(self):
        self.generation += 1
        reply, self.reply = self.reply, None
        if reply is not None:
            reply.abort()

    def get(self, port, path, tag):
        self.cancel()
        generation = self.generation
        request = QNetworkRequest(QUrl(f"http://127.0.0.1:{int(port)}{path}"))
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        reply = self.reply = self.manager.get(request)
        reply.setReadBufferSize(64 * 1024)
        buffer, failure = bytearray(), []
        deadline = QTimer(reply)
        deadline.setSingleShot(True)

        def fail(reason):
            if not failure:
                failure.append(reason)
                # Queue abort rather than re-entering network callbacks from readyRead.
                # The reply context cancels this callback if it is deleted first.
                QTimer.singleShot(0, reply, reply.abort)

        def read():
            chunk = bytes(reply.readAll())
            if failure:
                return
            buffer.extend(chunk)
            if len(buffer) > self.MAX_BYTES:
                buffer.clear()
                fail("Odpowiedź API przekracza limit 8 MiB.")

        def finished():
            deadline.stop()
            if generation != self.generation:
                reply.deleteLater()
                return
            self.reply = None
            if not failure:
                read()
            code = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            error, data = "", None
            if failure:
                error = failure[0]
            elif code != 200 or reply.error() != QNetworkReply.NetworkError.NoError:
                error = (f"API: HTTP {code}. Sprawdź bazę i wersję uruchomionego API."
                         if code else "Brak połączenia z API. Uruchom python -m edge.api.")
            else:
                try:
                    data = json.loads(buffer)
                    if not isinstance(data, dict):
                        raise ValueError()
                except (ValueError, UnicodeError, RecursionError):
                    error = "API zwróciło niepoprawny JSON."
            reply.deleteLater()
            self.result.emit(tag, data, error)

        reply.readyRead.connect(read)
        reply.finished.connect(finished)
        deadline.timeout.connect(lambda: fail("API nie odpowiedziało w wyznaczonym czasie."))
        deadline.start(self.timeout_ms)
