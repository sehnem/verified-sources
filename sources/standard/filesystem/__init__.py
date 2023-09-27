"""This source collects fsspec files."""
import io
from io import BytesIO, IOBase
from typing import Any, Dict, Iterator, List, Optional

import dlt
from dlt.common.storages.configuration import FileSystemCredentials
from dlt.common.storages.filesystem import FileItem
from fsspec import AbstractFileSystem  # type: ignore

from .helpers import FilesystemConfigurationResource, client_from_credentials, get_files
from .settings import DEFAULT_CHUNK_SIZE


class FileSystemDict(Dict[str, Any]):
    """A dictionary with the filesystem client."""

    def __init__(
        self, mapping: FileItem, credentials: Optional[FileSystemCredentials] = None
    ):
        """Create a dictionary with the filesystem client.

        Args:
            mapping (FileItem): The file item TypedDict.
            credentials (FileSystemCredentials): The credentials to the filesystem.
        """
        self.credentials = credentials
        super().__init__(**mapping)

    @property
    def filesystem(self) -> AbstractFileSystem:
        """The filesystem client based on the given credentials.

        Returns:
            AbstractFileSystem: The filesystem client.
        """
        if not self.credentials:
            raise ValueError("No credentials provided for the filesystem.")
        return client_from_credentials(self["file_url"], self.credentials)

    def open(self, **kwargs: Any) -> IOBase:  # noqa: A003
        """Open the file as a fsspec file.

        Args:
            **kwargs (Any): The arguments to pass to the fsspec open function.

        Returns:
            IOBase: The fsspec file.
        """
        opened_file: IOBase
        # if the user has already extracted the content, we use it so there will be no need to
        # download the file again.
        if self["file_content"] in self:
            bytes_io = BytesIO(self["file_content"])

            text_kwargs = {
                k: kwargs.pop(k)
                for k in ["encoding", "errors", "newline"]
                if k in kwargs
            }
            return io.TextIOWrapper(
                bytes_io,
                **text_kwargs,
            )
        else:
            opened_file = self.filesystem.open(self["file_url"], **kwargs)
        return opened_file

    def read_bytes(self) -> bytes:
        """Read the file content.

        Returns:
            bytes: The file content.
        """
        content: bytes
        # same as open, if the user has already extracted the content, we use it.
        if "file_content" in self:
            content = self["file_content"]
        else:
            content = self.filesystem.read_bytes(self["file_url"])
        return content


@dlt.resource(
    name="filesystem",
    merge_key="file_url",
    primary_key="file_url",
    spec=FilesystemConfigurationResource,
)
def filesystem_resource(
    bucket_url: str = dlt.secrets.value,
    credentials: FileSystemCredentials = dlt.secrets.value,
    filename_filter: Optional[str] = None,
    chunksize: int = DEFAULT_CHUNK_SIZE,
    extract_content: bool = False,
) -> Iterator[List[FileSystemDict]]:
    """This source collect files and download or extract data from them.

    Args:
        bucket_url (str): The url to the bucket.
        credentials (FileSystemCredentials): The credentials to the filesystem.
        filename_filter (str, optional): The filter to apply to the files in glob format.
        chunksize (int, optional): The number of files to process at once, defaults to 10.
        extract_content (bool, optional): If true, the content of the file will be extracted if
            false it will return a fsspec file, defaults to False.

    Returns:
        TDataItems: The list of files.
    """

    fs_client = client_from_credentials(bucket_url, credentials)

    # as it is a glob, we add a wildcard if no filter is given
    if not filename_filter:
        filename_filter = "*"

    files_chunk: List[FileSystemDict] = []
    for file_model in get_files(fs_client, bucket_url, filename_filter):
        file_dict = FileSystemDict(file_model, credentials)
        if extract_content:
            file_dict["file_content"] = file_dict.read_bytes()
        files_chunk.append(file_dict)

        # wait for the chunk to be full
        if len(file_dict) >= chunksize:
            yield files_chunk
            files_chunk = []
    if files_chunk:
        yield files_chunk
