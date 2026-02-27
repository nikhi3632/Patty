import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import httpx

from src.config import get
from supabase import create_client
from supabase.lib.client_options import SyncClientOptions
from storage3._sync.client import SyncStorageClient
from storage3.utils import SyncClient as StorageHttpClient

# Fix: supabase storage forces HTTP/2 which causes SSL errors on large uploads.
# Disable HTTP/2 and disable keepalive to force fresh TLS connections per request.


def create_session_http1(self, base_url, headers, timeout, verify=True, proxy=None):
    return StorageHttpClient(
        base_url=base_url,
        headers=headers,
        timeout=timeout,
        proxy=proxy,
        verify=bool(verify),
        follow_redirects=True,
        http2=False,
        limits=httpx.Limits(max_keepalive_connections=0),
    )


SyncStorageClient._create_session = create_session_http1

supabase = create_client(
    get("SUPABASE_URL"),
    get("SUPABASE_SERVICE_ROLE_KEY"),
    options=SyncClientOptions(storage_client_timeout=120),
)
