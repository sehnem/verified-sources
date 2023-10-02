"""Helpers for the filesystem resource."""
import mimetypes
import posixpath
from typing import Iterable, Optional
from urllib.parse import urlparse

from dlt.common.configuration.specs import configspec
from dlt.common.storages import filesystem
from dlt.common.storages.configuration import (
    FilesystemConfiguration,
    FileSystemCredentials,
)
from dlt.common.storages.filesystem import MTIME_DISPATCH
from dlt.common.storages.filesystem import FileItem
from fsspec import AbstractFileSystem  # type: ignore
from pendulum import DateTime


@configspec
class FilesystemConfigurationResource(FilesystemConfiguration):
    storage_path: Optional[str]
    start_date: Optional[DateTime]


def client_from_credentials(
    bucket_url: str, credentials: FileSystemCredentials
) -> AbstractFileSystem:
    """Create a filesystem client from the credentials.

    Args:
        bucket_url (str): The url to the bucket.
        credentials (FileSystemCredentials): The credentials to the filesystem.

    Returns:
        AbstractFileSystem: The filesystem client.
    """
    fs_client, _ = filesystem(bucket_url, credentials)
    return fs_client


def get_files(
    fs_client: AbstractFileSystem, bucket_url: str, file_glob: str = "**/*"
) -> Iterable[FileItem]:
    """Get the files from the filesystem client.

    Args:
        fs_client (AbstractFileSystem): The filesystem client.
        bucket_url (str): The url to the bucket.
        file_glob (str): A glob for the filename filter.

    Returns:
        Iterable[FileItem]: The list of files.
    """
    bucket_url_parsed = urlparse(bucket_url)
    protocol = bucket_url_parsed.scheme or "file"
    # absolute paths are not joined, so we remove it from the bucket_url path
    bucket_url_str = posixpath.join(
        bucket_url_parsed.netloc, bucket_url_parsed.path.lstrip("/")
    )
    filter_url = posixpath.join(bucket_url_str, file_glob)

    if bucket_url.startswith("file:///"):
        filter_url = posixpath.join("/", filter_url)

    glob_result = fs_client.glob(filter_url, detail=True)

    for file, md in glob_result.items():
        if md["type"] != "file":
            continue
        file_name = file.replace(bucket_url_str, "").lstrip("/")
        file_url = f"{protocol}://{file}"
        yield FileItem(
            file_name=file_name,
            file_url=file_url,
            mime_type=mimetypes.guess_type(file)[0],
            modification_date=MTIME_DISPATCH[protocol](md),
            file_content=None,
            size_in_bytes=int(md["size"]),
        )
