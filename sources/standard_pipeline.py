import json
import os
import posixpath
from typing import Iterable

import dlt
from dlt.common.time import ensure_pendulum_datetime

try:
    from .standard.filesystem import FileSystemDict, filesystem_resource  # type: ignore
    from .standard.inbox import inbox_source  # type: ignore
except ImportError:
    from standard.filesystem import filesystem_resource, FileSystemDict
    from standard.inbox import inbox_source

import pandas as pd
import pyarrow.parquet as pq  # type: ignore
from dlt.extract.source import TDataItem

TESTS_BUCKET_URL = posixpath.abspath("../tests/standard/samples/")


@dlt.transformer(name="filesystem")
def copy_files(
    items: Iterable[FileSystemDict],
    storage_path: str,
) -> TDataItem:
    """Reads files and copy them to local directory.

    Args:
        items (TDataItems): The list of files to copy.
        storage_path (str, optional): The path to store the files.

    Returns:
        TDataItem: The list of files copied.
    """
    storage_path = os.path.abspath(storage_path)
    os.makedirs(storage_path, exist_ok=True)
    for file_obj in items:
        file_dst = os.path.join(storage_path, file_obj["file_name"])
        file_obj["path"] = file_dst
        with open(file_dst, "wb") as f:
            f.write(file_obj.read_bytes())
        yield file_obj


@dlt.transformer(
    table_name="met_data",
    merge_key="date",
    primary_key="date",
    write_disposition="merge",
)
def extract_met_csv(
    items: Iterable[FileSystemDict],
    incremental: dlt.sources.incremental[str] = dlt.sources.incremental(
        "date",
        primary_key="date",
        initial_value="2023-01-01",
        allow_external_schedulers=True,
    ),
    chunksize: int = 15,
) -> TDataItem:
    """Reads file content and extract the data.

    This example shows how to use the incremental source to keep track of the last value, it can be
    used to keep track of the last date or id when fetching files that are continuously updated and
    have a date or id column, avoiding to process the same data twice.

    Args:
        item (TDataItem): The list of files to copy.
        incremental (dlt.sources.incremental[str], optional): The incremental source.

    Returns:
        TDataItem: The file content
    """
    for file_obj in items:
        # Here we use pandas chunksize to read the file in chunks and avoid loading the whole file
        # in memory.
        for df in pd.read_csv(
            file_obj.open(),
            usecols=["code", "date", "temperature"],
            parse_dates=["date"],
            chunksize=chunksize,
        ):
            # Ensure that the dates are pendulum datetime objects
            last_value = ensure_pendulum_datetime(incremental.last_value)
            df["date"] = df["date"].apply(ensure_pendulum_datetime)
            # Filter the data by the last value avoiding processing twice the same data
            df = df[df["date"] > last_value]
            yield df.to_dict(orient="records")


@dlt.transformer
def read_jsonl(
    items: Iterable[FileSystemDict],
    chunksize: int = 10,
) -> TDataItem:
    """Reads jsonl file content and extract the data.

    Args:
        item (Iterable[FileSystemDict]): The list of files to copy.
        chunksize (int, optional): The number of files to process at once, defaults to 10.

    Returns:
        TDataItem: The file content
    """
    for file_obj in items:
        with file_obj.open() as f:
            lines_chunk = []
            for line in f:
                lines_chunk.append(json.loads(line))
                if len(lines_chunk) >= chunksize:
                    yield lines_chunk
                    lines_chunk = []
        if lines_chunk:
            yield lines_chunk


@dlt.transformer
def read_parquet(
    items: Iterable[FileSystemDict],
    chunksize: int = 10,
) -> TDataItem:
    """Reads parquet file content and extract the data.

    Args:
        item (Iterable[FileSystemDict]): The list of files to copy.
        chunksize (int, optional): The number of files to process at once, defaults to 10.

    Returns:
        TDataItem: The file content
    """
    for file_obj in items:
        with file_obj.open() as f:
            parquet_file = pq.ParquetFile(f)
            for rows in parquet_file.iter_batches(batch_size=chunksize):
                yield rows.to_pylist()


def imap_inbox() -> None:
    # configure the pipeline with your destination details
    pipeline = dlt.pipeline(
        pipeline_name="standard_inbox",
        destination="duckdb",
        dataset_name="standard_inbox_data",
        full_refresh=True,
    )

    data_source = inbox_source(
        filter_by_emails=("josue@sehnem.com",),
        attachments=True,
        chunksize=10,
    )

    data_resource = data_source.resources["attachments"] | copy_files(
        storage_path="standard/files"
    )
    # run the pipeline with your parameters
    load_info = pipeline.run(data_resource)
    # pretty print the information on data that was loaded
    print(load_info)


def imap_messages() -> None:
    pipeline = dlt.pipeline(
        pipeline_name="standard_inbox",
        destination="duckdb",
        dataset_name="standard_inbox_data",
        full_refresh=True,
    )

    filter_emails = ("astra92293@gmail.com", "josue@sehnem.com")

    data_source = inbox_source(
        filter_by_emails=filter_emails,
        attachments=False,
        chunksize=10,
    )
    data_resource = data_source.resources["messages"]
    # run the pipeline with your parameters
    load_info = pipeline.run(data_resource)
    # pretty print the information on data that was loaded
    print(load_info)


def copy_files_resource() -> None:
    pipeline = dlt.pipeline(
        pipeline_name="standard_filesystem",
        destination="duckdb",
        dataset_name="standard_filesystem_data",
        full_refresh=True,
    )

    file_source = filesystem_resource(
        bucket_url=TESTS_BUCKET_URL,
        chunksize=10,
        extract_content=True,
    ) | copy_files(storage_path="standard/files")

    # run the pipeline with your parameters
    load_info = pipeline.run(file_source)
    # pretty print the information on data that was loaded
    print(load_info)


def read_file_content_resource() -> None:
    pipeline = dlt.pipeline(
        pipeline_name="standard_filesystem",
        destination="duckdb",
        dataset_name="met_data",
    )

    # When using the filesystem resource, you can specify a filter to select only the files you
    # want to load including a glob pattern. If you use a recursive glob pattern, the filenames
    # will include the path to the file inside the bucket_url.
    csv_source = (
        filesystem_resource(
            bucket_url=TESTS_BUCKET_URL,
            file_glob="*/*.csv",
            extract_content=True,
        )
        | extract_met_csv
    )

    csv_source.table_name = "met_data"
    # run the pipeline with your parameters
    load_info = pipeline.run(csv_source)
    # pretty print the information on data that was loaded
    print(load_info)

    # JSONL reading
    jsonl_source = (
        filesystem_resource(bucket_url=TESTS_BUCKET_URL, file_glob="jsonl/*.jsonl")
        | read_jsonl
    )

    jsonl_source.table_name = "jsonl_data"
    # run the pipeline with your parameters
    load_info = pipeline.run(jsonl_source)
    # pretty print the information on data that was loaded
    print(load_info)

    # PARQUET reading
    parquet_source = (
        filesystem_resource(bucket_url=TESTS_BUCKET_URL, file_glob="parquet/*.parquet")
        | read_parquet
    )

    parquet_source.table_name = "parquet_data"
    # run the pipeline with your parameters
    load_info = pipeline.run(parquet_source)
    # pretty print the information on data that was loaded
    print(load_info)


if __name__ == "__main__":
    # copy_files_resource()
    # read_file_content_resource()
    # imap_inbox()
    imap_messages()