"""Amazon Glue Catalog Module."""

from awswrangler.catalog._add import add_csv_partitions, add_parquet_partitions  # noqa
from awswrangler.catalog._create import (  # noqa
    create_csv_table,
    create_database,
    create_parquet_table,
    overwrite_table_parameters,
    upsert_table_parameters,
)
from awswrangler.catalog._delete import delete_database, delete_table_if_exists  # noqa
from awswrangler.catalog._get import (  # noqa
    databases,
    get_columns_comments,
    get_connection,
    get_csv_partitions,
    get_databases,
    get_engine,
    get_parquet_partitions,
    get_partitions,
    get_table_description,
    get_table_location,
    get_table_parameters,
    get_table_types,
    get_tables,
    search_tables,
    table,
    tables,
)
from awswrangler.catalog._utils import (  # noqa
    does_table_exist,
    drop_duplicated_columns,
    extract_athena_types,
    sanitize_column_name,
    sanitize_dataframe_columns_names,
    sanitize_table_name,
)
