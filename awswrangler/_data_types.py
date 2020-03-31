"""Internal (private) Data Types Module."""

import logging
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import pandas as pd  # type: ignore
import pyarrow as pa  # type: ignore
import pyarrow.parquet  # type: ignore

from awswrangler import exceptions

_logger: logging.Logger = logging.getLogger(__name__)


def athena2pyarrow(dtype: str) -> pa.DataType:  # pylint: disable=too-many-return-statements
    """Athena to PyArrow data types conversion."""
    dtype = dtype.lower()
    if dtype == "tinyint":
        return pa.int8()
    if dtype == "smallint":
        return pa.int16()
    if dtype in ("int", "integer"):
        return pa.int32()
    if dtype == "bigint":
        return pa.int64()
    if dtype == "float":
        return pa.float32()
    if dtype == "double":
        return pa.float64()
    if dtype == "boolean":
        return pa.bool_()
    if dtype in ("string", "char", "varchar", "array", "row", "map"):
        return pa.string()
    if dtype == "timestamp":
        return pa.timestamp(unit="ns")
    if dtype == "date":
        return pa.date32()
    if dtype in ("binary" or "varbinary"):
        return pa.binary()
    if dtype.startswith("decimal"):
        precision, scale = dtype.replace("decimal(", "").replace(")", "").split(sep=",")
        return pa.decimal128(precision=int(precision), scale=int(scale))
    raise exceptions.UnsupportedType(f"Unsupported Athena type: {dtype}")  # pragma: no cover


def pyarrow2athena(dtype: pa.DataType) -> str:  # pylint: disable=too-many-branches,too-many-return-statements
    """Pyarrow to Athena data types conversion."""
    if pa.types.is_int8(dtype):
        return "tinyint"
    if pa.types.is_int16(dtype):
        return "smallint"
    if pa.types.is_int32(dtype):
        return "int"
    if pa.types.is_int64(dtype):
        return "bigint"
    if pa.types.is_float32(dtype):
        return "float"
    if pa.types.is_float64(dtype):
        return "double"
    if pa.types.is_boolean(dtype):
        return "boolean"
    if pa.types.is_string(dtype):
        return "string"
    if pa.types.is_timestamp(dtype):
        return "timestamp"
    if pa.types.is_date(dtype):
        return "date"
    if pa.types.is_binary(dtype):
        return "binary"
    if pa.types.is_dictionary(dtype):
        return pyarrow2athena(dtype=dtype.value_type)
    if pa.types.is_decimal(dtype):
        return f"decimal({dtype.precision},{dtype.scale})"
    if pa.types.is_list(dtype):
        return f"array<{pyarrow2athena(dtype=dtype.value_type)}>"
    if pa.types.is_struct(dtype):  # pragma: no cover
        return f"struct<{', '.join([f'{f.name}: {pyarrow2athena(dtype=f.type)}' for f in dtype])}>"
    if dtype == pa.null():
        raise exceptions.UndetectedType("We can not infer the data type from an entire null object column")
    raise exceptions.UnsupportedType(f"Unsupported Pyarrow type: {dtype}")  # pragma: no cover


def pyarrow2pandas_extension(  # pylint: disable=too-many-branches,too-many-return-statements
    dtype: pa.DataType
) -> Optional[pd.api.extensions.ExtensionDtype]:
    """Pyarrow to Pandas data types conversion."""
    if pa.types.is_int8(dtype):  # pragma: no cover
        return pd.Int8Dtype()
    if pa.types.is_int16(dtype):  # pragma: no cover
        return pd.Int16Dtype()
    if pa.types.is_int32(dtype):
        return pd.Int32Dtype()
    if pa.types.is_int64(dtype):
        return pd.Int64Dtype()
    if pa.types.is_boolean(dtype):
        return pd.BooleanDtype()
    if pa.types.is_string(dtype):
        return pd.StringDtype()
    return None


def athena2pandas(dtype: str) -> str:  # pylint: disable=too-many-branches,too-many-return-statements
    """Athena to Pandas data types conversion."""
    dtype = dtype.lower()
    if dtype == "tinyint":
        return "Int8"
    if dtype == "smallint":
        return "Int16"
    if dtype in ("int", "integer"):
        return "Int32"
    if dtype == "bigint":
        return "Int64"
    if dtype == "float":
        return "float32"
    if dtype == "double":
        return "float64"
    if dtype == "boolean":
        return "boolean"
    if dtype in ("string", "char", "varchar"):
        return "string"
    if dtype in ("timestamp", "timestamp with time zone"):
        return "datetime64"
    if dtype == "date":
        return "date"
    if dtype.startswith("decimal"):
        return "decimal"
    if dtype in ("binary", "varbinary"):
        return "bytes"
    if dtype == "array":
        return "list"
    raise exceptions.UnsupportedType(f"Unsupported Athena type: {dtype}")  # pragma: no cover


def pyarrow_types_from_pandas(
    df: pd.DataFrame, index: bool, ignore_cols: Optional[List[str]] = None
) -> Dict[str, pa.DataType]:
    """Extract the related Pyarrow data types from any Pandas DataFrame."""
    # Handle exception data types (e.g. Int64, Int32, string)
    ignore_cols = [] if ignore_cols is None else ignore_cols
    cols: List[str] = []
    cols_dtypes: Dict[str, Optional[pa.DataType]] = {}
    for name, dtype in df.dtypes.to_dict().items():
        dtype = str(dtype)
        if name in ignore_cols:
            cols_dtypes[name] = None
        elif dtype == "Int8":
            cols_dtypes[name] = pa.int8()
        elif dtype == "Int16":
            cols_dtypes[name] = pa.int16()
        elif dtype == "Int32":
            cols_dtypes[name] = pa.int32()
        elif dtype == "Int64":
            cols_dtypes[name] = pa.int64()
        elif dtype == "string":
            cols_dtypes[name] = pa.string()
        else:
            cols.append(name)

    # Filling cols_dtypes and indexes
    indexes: List[str] = []
    for field in pa.Schema.from_pandas(df=df[cols], preserve_index=index):
        name = str(field.name)
        cols_dtypes[name] = field.type
        if (name not in df.columns) and (index is True):
            indexes.append(name)

    # Filling schema
    columns_types: Dict[str, pa.DataType]
    columns_types = {n: cols_dtypes[n] for n in list(df.columns) + indexes}  # add cols + indexes
    _logger.debug(f"columns_types: {columns_types}")
    return columns_types


def athena_types_from_pandas(
    df: pd.DataFrame, index: bool, cast_columns: Optional[Dict[str, str]] = None
) -> Dict[str, str]:
    """Extract the related Athena data types from any Pandas DataFrame."""
    casts: Dict[str, str] = cast_columns if cast_columns else {}
    pa_columns_types: Dict[str, Optional[pa.DataType]] = pyarrow_types_from_pandas(
        df=df, index=index, ignore_cols=list(casts.keys())
    )
    athena_columns_types: Dict[str, str] = {}
    for k, v in pa_columns_types.items():
        if v is None:
            athena_columns_types[k] = casts[k]
        else:
            athena_columns_types[k] = pyarrow2athena(dtype=v)
    _logger.debug(f"athena_columns_types: {athena_columns_types}")
    return athena_columns_types


def athena_types_from_pandas_partitioned(
    df: pd.DataFrame,
    index: bool,
    partition_cols: Optional[List[str]] = None,
    cast_columns: Optional[Dict[str, str]] = None,
) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Extract the related Athena data types from any Pandas DataFrame considering possible partitions."""
    partitions: List[str] = partition_cols if partition_cols else []
    athena_columns_types: Dict[str, str] = athena_types_from_pandas(df=df, index=index, cast_columns=cast_columns)
    columns_types: Dict[str, str] = {}
    partitions_types: Dict[str, str] = {}
    for k, v in athena_columns_types.items():
        if k in partitions:
            partitions_types[k] = v
        else:
            columns_types[k] = v
    return columns_types, partitions_types


def pyarrow_schema_from_pandas(
    df: pd.DataFrame,
    index: bool,
    ignore_cols: Optional[List[str]] = None,
    cast_columns: Optional[Dict[str, str]] = None,
) -> pa.Schema:
    """Extract the related Pyarrow Schema from any Pandas DataFrame."""
    casts: Dict[str, str] = {} if cast_columns is None else cast_columns
    ignore: List[str] = [] if ignore_cols is None else ignore_cols
    ignore = ignore + list(casts.keys())
    columns_types: Dict[str, Optional[pa.DataType]] = pyarrow_types_from_pandas(df=df, index=index, ignore_cols=ignore)
    for k, v in casts.items():
        if k in df.columns:
            columns_types[k] = athena2pyarrow(v)
    columns_types = {k: v for k, v in columns_types.items() if v is not None}
    _logger.debug(f"columns_types: {columns_types}")
    return pa.schema(fields=columns_types)


def athena_types_from_pyarrow_schema(
    schema: pa.Schema, partitions: pyarrow.parquet.ParquetPartitions
) -> Tuple[Dict[str, str], Optional[Dict[str, str]]]:
    """Extract the related Athena data types from any PyArrow Schema considering possible partitions."""
    columns_types: Dict[str, str] = {str(f.name): pyarrow2athena(dtype=f.type) for f in schema}
    _logger.debug(f"columns_types: {columns_types}")
    partitions_types: Dict[str, str] = {p.name: pyarrow2athena(p.dictionary.type) for p in partitions}
    _logger.debug(f"partitions_types: {partitions_types}")
    return columns_types, partitions_types


def athena_partitions_from_pyarrow_partitions(
    path: str, partitions: pyarrow.parquet.ParquetPartitions
) -> Dict[str, List[str]]:
    """Extract the related Athena partitions values from any PyArrow Partitions."""
    path = path if path[-1] == "/" else f"{path}/"
    partitions_values: Dict[str, List[str]] = {}
    names: List[str] = [p.name for p in partitions]
    for values in zip(*[p.keys for p in partitions]):
        suffix: str = "/".join([f"{n}={v}" for n, v in zip(names, values)])
        suffix = suffix if suffix[-1] == "/" else f"{suffix}/"
        partitions_values[f"{path}{suffix}"] = list(values)
    return partitions_values


def cast_pandas_with_athena_types(df: pd.DataFrame, cast_columns: Dict[str, str]) -> pd.DataFrame:
    """Cast columns in a Pandas DataFrame."""
    for col, athena_type in cast_columns.items():
        if col in df.columns:
            pandas_type: str = athena2pandas(dtype=athena_type)
            if pandas_type == "datetime64":
                df[col] = pd.to_datetime(df[col])
            elif pandas_type == "date":
                df[col] = pd.to_datetime(df[col]).dt.date.replace(to_replace={pd.NaT: None})
            elif pandas_type == "bytes":
                df[col] = df[col].astype("string").str.encode(encoding="utf-8").replace(to_replace={pd.NA: None})
            elif pandas_type == "decimal":
                df[col] = (
                    df[col]
                    .astype("string")
                    .apply(lambda x: Decimal(str(x)) if str(x) not in ("", "none", " ", "<NA>") else None)
                )
            else:
                df[col] = df[col].astype(pandas_type)
    return df
