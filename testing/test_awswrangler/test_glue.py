import logging

import pytest
import boto3
import pandas as pd

from awswrangler import Session

logging.basicConfig(level=logging.INFO, format="[%(asctime)s][%(levelname)s][%(name)s][%(funcName)s] %(message)s")
logging.getLogger("awswrangler").setLevel(logging.DEBUG)


@pytest.fixture(scope="module")
def cloudformation_outputs():
    response = boto3.client("cloudformation").describe_stacks(StackName="aws-data-wrangler-test")
    outputs = {}
    for output in response.get("Stacks")[0].get("Outputs"):
        outputs[output.get("OutputKey")] = output.get("OutputValue")
    yield outputs


@pytest.fixture(scope="module")
def session():
    yield Session()


@pytest.fixture(scope="module")
def bucket(session, cloudformation_outputs):
    if "BucketName" in cloudformation_outputs:
        bucket = cloudformation_outputs.get("BucketName")
        session.s3.delete_objects(path=f"s3://{bucket}/")
    else:
        raise Exception("You must deploy the test infrastructure using SAM!")
    yield bucket
    session.s3.delete_objects(path=f"s3://{bucket}/")


@pytest.fixture(scope="module")
def database(cloudformation_outputs):
    if "GlueDatabaseName" in cloudformation_outputs:
        database = cloudformation_outputs.get("GlueDatabaseName")
    else:
        raise Exception("You must deploy the test infrastructure using SAM!")
    yield database


@pytest.fixture(scope="module")
def table(
    session,
    bucket,
    database,
):
    dataframe = pd.read_csv("data_samples/micro.csv")
    path = f"s3://{bucket}/test/"
    table = "test"
    session.pandas.to_parquet(dataframe=dataframe,
                              database=database,
                              table=table,
                              path=path,
                              preserve_index=False,
                              mode="overwrite",
                              procs_cpu_bound=1,
                              partition_cols=["name", "date"])
    yield table
    session.glue.delete_table_if_exists(database=database, table=table)
    session.s3.delete_objects(path=path)


def test_get_athena_types(session, database, table):
    dtypes = session.glue.get_table_athena_types(database=database, table=table)
    assert dtypes["id"] == "bigint"
    assert dtypes["value"] == "double"
    assert dtypes["name"] == "string"
    assert dtypes["date"] == "string"


def test_get_table_python_types(session, database, table):
    ptypes = session.glue.get_table_python_types(database=database, table=table)
    assert ptypes["id"] == int
    assert ptypes["value"] == float
    assert ptypes["name"] == str
    assert ptypes["date"] == str


def test_get_databases(session, database):
    dbs = list(session.glue.get_databases())
    assert len(dbs) > 0
    for db in dbs:
        if db["Name"] == database:
            assert db["Description"] == "AWS Data Wrangler Test Arena - Glue Database"


def test_get_tables(session, table):
    tables = list(session.glue.get_tables())
    assert len(tables) > 0
    for tbl in tables:
        if tbl["Name"] == table:
            assert tbl["TableType"] == "EXTERNAL_TABLE"


def test_get_tables_database(session, database):
    tables = list(session.glue.get_tables(database=database))
    assert len(tables) > 0
    for tbl in tables:
        assert tbl["DatabaseName"] == database


def test_get_tables_search(session, table):
    tables = list(session.glue.search_tables(text="parquet"))
    assert len(tables) > 0
    for tbl in tables:
        if tbl["Name"] == table:
            assert tbl["TableType"] == "EXTERNAL_TABLE"


def test_get_tables_prefix(session, table):
    tables = list(session.glue.get_tables(prefix=table[:-1]))
    assert len(tables) > 0
    for tbl in tables:
        if tbl["Name"] == table:
            assert tbl["TableType"] == "EXTERNAL_TABLE"


def test_get_tables_suffix(session, table):
    tables = list(session.glue.get_tables(suffix=table[1:]))
    assert len(tables) > 0
    for tbl in tables:
        if tbl["Name"] == table:
            assert tbl["TableType"] == "EXTERNAL_TABLE"


def test_glue_utils(session, database, table):
    assert len(session.glue.databases().index) > 0
    assert len(session.glue.tables().index) > 0
    assert len(session.glue.table(database=database, name=table).index) > 0


def test_glue_tables_full(session, database, table):
    assert len(
        session.glue.tables(database=database,
                            search_text="parquet",
                            name_contains=table[1:-1],
                            name_prefix=table[0],
                            name_suffix=table[-1]).index) > 0
