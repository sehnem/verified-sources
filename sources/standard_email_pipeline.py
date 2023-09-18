import dlt

try:
    from .standard.inbox import inbox_source
except ImportError:
    from standard.inbox import inbox_source


def from_standard_inbox() -> None:
    # configure the pipeline with your destination details
    pipeline = dlt.pipeline(
        pipeline_name="standard_inbox",
        destination="duckdb",
        dataset_name="standard_inbox_data",
        full_refresh=True,
    )

    # filter_emails = ("astra92293@gmail.com", "josue@sehnem.com")

    data_source = inbox_source(
        # filter_by_emails=filter_emails,
        attachments=True,
        chunksize=10,
        filter_by_mime_type=("application/pdf",),
    )
    data_resource = data_source.resources["attachments"]
    # run the pipeline with your parameters
    load_info = pipeline.run(data_resource)
    # pretty print the information on data that was loaded
    print(load_info)

    data_source = inbox_source(
        # filter_by_emails=filter_emails,
        attachments=False,
        chunksize=10,
    )
    data_resource = data_source.resources["messages"]
    # run the pipeline with your parameters
    load_info = pipeline.run(data_resource)
    # pretty print the information on data that was loaded
    print(load_info)


if __name__ == "__main__":
    from_standard_inbox()