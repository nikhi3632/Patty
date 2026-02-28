import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import httpx

from src.config import get
from supabase import create_client
from supabase.lib.client_options import SyncClientOptions
from postgrest._sync.client import SyncPostgrestClient
from postgrest.utils import SyncClient as PostgrestHttpClient
from storage3._sync.client import SyncStorageClient
from storage3.utils import SyncClient as StorageHttpClient

# Fix: supabase forces HTTP/2 which causes "Resource temporarily unavailable"
# errors under concurrent requests. Disable HTTP/2 for both PostgREST and storage.


def postgrest_session_http1(self, base_url, headers, timeout, verify=True, proxy=None):
    return PostgrestHttpClient(
        base_url=base_url,
        headers=headers,
        timeout=timeout,
        verify=bool(verify),
        proxy=proxy,
        follow_redirects=True,
        http2=False,
    )


def storage_session_http1(self, base_url, headers, timeout, verify=True, proxy=None):
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


SyncPostgrestClient.create_session = postgrest_session_http1
SyncStorageClient._create_session = storage_session_http1


class LazySupabase:
    """Proxy that defers Supabase client creation until first use.

    Avoids connection attempts at import time, which makes tests and
    startup more robust when .env isn't available.
    """

    instance = None

    def __getattr__(self, name):
        if LazySupabase.instance is None:
            LazySupabase.instance = create_client(
                get("SUPABASE_URL"),
                get("SUPABASE_SERVICE_ROLE_KEY"),
                options=SyncClientOptions(storage_client_timeout=120),
            )
        return getattr(LazySupabase.instance, name)


supabase = LazySupabase()
