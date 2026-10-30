from django.conf import settings
from django.core.files.uploadhandler import MemoryFileUploadHandler, StopUpload


class ReceiptMemoryUploadHandler(MemoryFileUploadHandler):
    """Bound receipt file bytes while streaming, before retaining the whole file."""

    def receive_data_chunk(self, raw_data, start):
        if start + len(raw_data) > settings.RECEIPT_MAX_BYTES:
            raise StopUpload(connection_reset=False)
        return super().receive_data_chunk(raw_data, start)
