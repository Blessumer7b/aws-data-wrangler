"""Amazon S3 Module."""

import gzip
import multiprocessing as mp
from io import BytesIO
from logging import Logger, getLogger
from time import sleep
from typing import TYPE_CHECKING, Callable, Dict, Iterator, List, Optional, Union
from uuid import uuid4

import numpy as np  # type: ignore
import pandas as pd  # type: ignore
import pyarrow as pa  # type: ignore
from botocore.exceptions import ClientError  # type: ignore
from pandas.io.common import infer_compression  # type: ignore
from pyarrow import parquet as pq  # type: ignore

from awswrangler import _utils
from awswrangler.exceptions import InvalidCompression, S3WaitObjectTimeout

if TYPE_CHECKING:  # pragma: no cover
    from awswrangler.session import Session, _SessionPrimitives
    import boto3  # type: ignore

logger: Logger = getLogger(__name__)


class S3:
    """Amazon S3 Class."""
    def __init__(self, session: "Session"):
        """Amazon S3 Class Constructor.

        Note
        ----
        Don't use it directly, call through a Session().
        e.g. wr.SERVICE.FUNCTION() (Default Session)

        Parameters
        ----------
        session : awswrangler.Session()
            Wrangler's Session

        """
        self._session: "Session" = session

    def does_object_exists(self, path: str) -> bool:
        """Check if object exists on S3.

        Parameters
        ----------
        path: str
            S3 path (e.g. s3://bucket/key).

        Returns
        -------
        bool
            True if exists, False otherwise.

        Examples
        --------
        >>> import awswrangler as wr
        >>> wr.s3.does_object_exists("s3://bucket/key_real")
        True
        >>> wr.s3.does_object_exists("s3://bucket/key_unreal")
        False

        """
        bucket: str
        key: str
        bucket, key = path.replace("s3://", "").split("/", 1)
        try:
            self._session.s3_client.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError as ex:
            if ex.response["ResponseMetadata"]["HTTPStatusCode"] == 404:
                return False
            raise ex  # pragma: no cover

    def wait_object_exists(self, path: str, polling_sleep: float = 0.1, timeout: Optional[float] = 10.0) -> None:
        """Wait object exists on S3.

        Parameters
        ----------
        path : str
            S3 path (e.g. s3://bucket/key).
        polling_sleep : float
            Sleep between each retry (Seconds).
        timeout : float, optional
            Timeout (Seconds).

        Returns
        -------
        None
            None

        Raises
        ------
        S3WaitObjectTimeout
            Raised in case of timeout.

        Examples
        --------
        >>> import awswrangler as wr
        >>> wr.s3.wait_object_exists("s3://bucket/key_expected")

        """
        time_acc: float = 0.0
        while self.does_object_exists(path=path) is False:
            sleep(polling_sleep)
            if timeout is not None:
                time_acc += polling_sleep
                if time_acc >= timeout:
                    raise S3WaitObjectTimeout(f"Waited for {path} for {time_acc} seconds")

    def get_bucket_region(self, bucket: str) -> str:
        """Get bucket region.

        Parameters
        ----------
        bucket : str
            Bucket name.

        Returns
        -------
        str
            Region code (e.g. "us-east-1").

        Examples
        --------
        >>> import awswrangler as wr
        >>> region = wr.s3.get_bucket_region("bucket-name")

        """
        logger.debug(f"bucket: {bucket}")
        region: str = self._session.s3_client.get_bucket_location(Bucket=bucket)["LocationConstraint"]
        region = "us-east-1" if region is None else region
        logger.debug(f"region: {region}")
        return region

    def list_objects(self, path: str) -> List[str]:
        """List Amazon S3 objects from a prefix.

        Parameters
        ----------
        path : str
            S3 path (e.g. s3://bucket/prefix).

        Returns
        -------
        List[str]
            List of objects paths.

        Examples
        --------
        >>> import awswrangler as wr
        >>> wr.s3.list_objects("s3://bucket/prefix")
        ["s3://bucket/prefix0", "s3://bucket/prefix1", "s3://bucket/prefix2"]

        """
        paginator = self._session.s3_client.get_paginator("list_objects_v2")
        bucket: str
        prefix: str
        bucket, prefix = _utils.parse_path(path=path)
        response_iterator = paginator.paginate(Bucket=bucket, Prefix=prefix, PaginationConfig={"PageSize": 1000})
        paths: List[str] = []
        for page in response_iterator:
            if page.get("Contents") is not None:
                for content in page.get("Contents"):
                    if (content is not None) and ("Key" in content):
                        key: str = content["Key"]
                        paths.append(f"s3://{bucket}/{key}")
        return paths

    def delete_objects_list(self, paths: List[str], parallel: bool = True) -> None:
        """Delete all listed Amazon S3 objects.

        Note
        ----
        In case of `parallel=True` the number of process that will be spawned will be get from os.cpu_count().

        Parameters
        ----------
        paths : str
            S3 path (e.g. s3://bucket/prefix).
        parallel : bool
            True to enable parallel requests, False to disable.

        Returns
        -------
        None
            None.

        Examples
        --------
        >>> import awswrangler as wr
        >>> wr.s3.delete_objects_list(["s3://bucket/key0", "s3://bucket/key1"])

        """
        if len(paths) < 1:
            return
        cpus: int = _utils.get_cpu_count(parallel=parallel)
        buckets: Dict[str, List[str]] = self._split_paths_by_bucket(paths=paths)
        for bucket, keys in buckets.items():
            if cpus == 1:
                self._delete_objects(s3_client=self._session.s3_client, bucket=bucket, keys=keys)
            else:
                _utils.parallelize(func=self._delete_objects_remote,
                                   session=self._session,
                                   lst=keys,
                                   extra_args=(bucket, ),
                                   has_return=False)

    @staticmethod
    def _delete_objects_remote(session_primitives: "_SessionPrimitives", keys: List[str], bucket: str) -> None:
        session: "Session" = session_primitives.build_session()
        s3_client: boto3.client = session.s3_client
        S3._delete_objects(s3_client=s3_client, bucket=bucket, keys=keys)

    @staticmethod
    def _delete_objects(s3_client: "boto3.session.Session.client", bucket: str, keys: List[str]) -> None:
        chunks: List[List[str]] = _utils.chunkify(lst=keys, max_length=1_000)
        logger.debug(f"len(chunks): {len(chunks)}")
        for chunk in chunks:
            batch: List[Dict[str, str]] = [{"Key": key} for key in chunk]
            s3_client.delete_objects(Bucket=bucket, Delete={"Objects": batch})

    @staticmethod
    def _split_paths_by_bucket(paths: List[str]) -> Dict[str, List[str]]:
        buckets: Dict[str, List[str]] = {}
        bucket: str
        key: str
        for path in paths:
            bucket, key = _utils.parse_path(path=path)
            if bucket not in buckets:
                buckets[bucket] = []
            buckets[bucket].append(key)
        return buckets

    def delete_objects_prefix(self, path: str, parallel: bool = True) -> None:
        """Delete all Amazon S3 objects under the received prefix.

        Note
        ----
        In case of `parallel=True` the number of process that will be spawned will be get from os.cpu_count().

        Parameters
        ----------
        path : str
            S3 prefix path (e.g. s3://bucket/prefix).
        parallel : bool
            True to enable parallel requests, False to disable.

        Returns
        -------
        None
            None.

        Examples
        --------
        >>> import awswrangler as wr
        >>> wr.s3.delete_objects_prefix(path="s3://bucket/prefix"])

        """
        paths: List[str] = self.list_objects(path=path)
        self.delete_objects_list(paths=paths, parallel=parallel)

    def _writer_factory(self,
                        file_writer: Callable,
                        df: pd.DataFrame,
                        path: str,
                        filename: Optional[str] = None,
                        partition_cols: Optional[List[str]] = None,
                        num_files: int = 1,
                        mode: str = "append",
                        parallel: bool = True,
                        self_destruct: bool = False,
                        **pd_kwargs) -> List[str]:
        cpus: int = _utils.get_cpu_count(parallel=parallel)
        paths: List[str] = []
        path = path if path[-1] == "/" else f"{path}/"
        if filename is not None:
            paths.append(
                file_writer(df=df, path=path, filename=filename, cpus=cpus, self_destruct=self_destruct, **pd_kwargs))
        else:
            if (mode == "overwrite") or ((mode == "partition_upsert") and (not partition_cols)):
                self.delete_objects_prefix(path=path, parallel=parallel)
            if not partition_cols:
                if num_files < 2:
                    paths.append(file_writer(df=df, path=path, cpus=cpus, self_destruct=self_destruct, **pd_kwargs))
                else:
                    for subgroup in np.array_split(df, num_files):
                        paths.append(
                            file_writer(df=subgroup, path=path, cpus=cpus, self_destruct=self_destruct, **pd_kwargs))
            else:
                for keys, subgroup in df.groupby(by=partition_cols, observed=True):
                    subgroup = subgroup.drop(partition_cols, axis="columns")
                    keys = (keys, ) if not isinstance(keys, tuple) else keys
                    subdir = "/".join([f"{name}={val}" for name, val in zip(partition_cols, keys)])
                    prefix: str = f"{path}{subdir}/"
                    if mode == "partition_upsert":
                        self.delete_objects_prefix(path=prefix, parallel=parallel)
                    paths.append(
                        file_writer(df=subgroup, path=prefix, cpus=cpus, self_destruct=self_destruct, **pd_kwargs))
        return paths

    def to_csv(self,
               df: pd.DataFrame,
               path: str,
               filename: Optional[str] = None,
               partition_cols: Optional[List[str]] = None,
               num_files: int = 1,
               mode: str = "append",
               parallel: bool = True,
               self_destruct: bool = False,
               **pd_kwargs) -> List[str]:
        """Write CSV file(s) on Amazon S3.

        Note
        ----
        In case of `parallel=True` the number of process that will be spawned will be get from os.cpu_count().

        Parameters
        ----------
        df: pandas.DataFrame
            Pandas DataFrame https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.DataFrame.html
        path : str
            S3 path (e.g. s3://bucket/prefix).
        filename : str, optional
            The default behavior (`filename=None`) uses random names, but if you prefer pass a filename.
            It will disable the partitioning.
        partition_cols: List[str], optional
            List of column names that will be used to create partitions.
        num_files: int
            Number of files to split the data. There is no effect when partition_cols or filename are used.
        mode: str
            "append", "overwrite", "partition_upsert"
        parallel : bool
            True to enable parallel requests, False to disable.
        self_destruct: bool
            Destroy the received DataFrame to deallocate memory during the write process.
        pd_kwargs:
            keyword arguments forwarded to pandas.DataFrame.to_csv()
            https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.DataFrame.to_csv.html

        Returns
        -------
        List[str]
            List with the s3 paths created.

        Examples
        --------
        Writing single file with filename

        >>> import awswrangler as wr
        >>> import pandas as pd
        >>> wr.s3.to_csv(
        ...     df=pd.DataFrame({"col": [1, 2, 3]}),
        ...     path="s3://bucket/prefix",
        ...     filename="my_file.csv"
        ... )

        Writing multiple files

        >>> import awswrangler as wr
        >>> import pandas as pd
        >>> wr.s3.to_csv(
        ...     df=pd.DataFrame({"col": [1, 2, 3]}),
        ...     path="s3://bucket/prefix",
        ...     num_files=4
        ... )

        Writing partitioned dataset

        >>> import awswrangler as wr
        >>> import pandas as pd
        >>> wr.s3.to_csv(
        ...     df=pd.DataFrame({
        ...         "col": [1, 2, 3],
        ...         "col2": ["A", "A", "B"]
        ...     }),
        ...     path="s3://bucket/prefix",
        ...     partition_cols=["col2"]
        ... )

        """
        return self._writer_factory(file_writer=self._write_csv_file,
                                    df=df,
                                    path=path,
                                    filename=filename,
                                    partition_cols=partition_cols,
                                    num_files=num_files,
                                    mode=mode,
                                    parallel=parallel,
                                    self_destruct=self_destruct,
                                    **pd_kwargs)

    def _write_csv_file(self,
                        df: pd.DataFrame,
                        path: str,
                        cpus: int,
                        filename: Optional[str] = None,
                        self_destruct: bool = False,
                        **pd_kwargs) -> str:
        compression: Optional[str] = pd_kwargs.get("compression")
        if compression is None:
            compression_ext: str = ""
        elif compression == "gzip":
            compression_ext = ".gz"
            pd_kwargs["compression"] = None
        else:
            raise InvalidCompression(f"{compression} is invalid, please use gzip.")  # pragma: no cover
        file_path: str = f"{path}{uuid4().hex}{compression_ext}.csv" if filename is None else f"{path}{filename}"
        if compression is None:
            file_obj: BytesIO = BytesIO(initial_bytes=bytes(df.to_csv(None, **pd_kwargs), "utf-8"))
        else:
            file_obj = BytesIO()
            with gzip.open(file_obj, 'wb') as f:
                f.write(df.to_csv(None, **pd_kwargs).encode(encoding="utf-8"))
            file_obj.seek(0)
        if self_destruct is True:
            df.drop(df.index, inplace=True)
            del df
        _utils.upload_fileobj(s3_client=self._session.s3_client, file_obj=file_obj, path=file_path, cpus=cpus)
        return file_path

    def to_parquet(self,
                   df: pd.DataFrame,
                   path: str,
                   filename: Optional[str] = None,
                   partition_cols: Optional[List[str]] = None,
                   num_files: int = 1,
                   mode: str = "append",
                   parallel: bool = True,
                   self_destruct: bool = False,
                   **pd_kwargs) -> List[str]:
        """Write Parquet file(s) on Amazon S3.

        Note
        ----
        In case of `parallel=True` the number of process that will be spawned will be get from os.cpu_count().

        Parameters
        ----------
        df: pandas.DataFrame
            Pandas DataFrame https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.DataFrame.html
        path : str
            S3 path (e.g. s3://bucket/prefix).
        filename : str, optional
            The default behavior (`filename=None`) uses random names, but if you prefer pass a filename.
            It will disable the partitioning.
        partition_cols: List[str], optional
            List of column names that will be used to create partitions.
        num_files: int
            Number of files to split the data. There is no effect when partition_cols or filename are used.
        mode: str
            "append", "overwrite", "partition_upsert"
        parallel : bool
            True to enable parallel requests, False to disable.
        self_destruct: bool
            Destroy the received DataFrame to deallocate memory during the write process.
        pd_kwargs:
            keyword arguments forwarded to pandas.DataFrame.to_parquet()
            https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.DataFrame.to_parquet.html

        Returns
        -------
        List[str]
            List with the s3 paths created.

        Examples
        --------
        Writing single file with filename

        >>> import awswrangler as wr
        >>> import pandas as pd
        >>> wr.s3.to_parquet(
        ...     df=pd.DataFrame({"col": [1, 2, 3]}),
        ...     path="s3://bucket/prefix",
        ...     filename="my_file.parquet"
        ... )

        Writing multiple files

        >>> import awswrangler as wr
        >>> import pandas as pd
        >>> wr.s3.to_parquet(
        ...     df=pd.DataFrame({"col": [1, 2, 3]}),
        ...     path="s3://bucket/prefix",
        ...     num_files=4
        ... )

        Writing partitioned dataset

        >>> import awswrangler as wr
        >>> import pandas as pd
        >>> wr.s3.to_parquet(
        ...     df=pd.DataFrame({
        ...         "col": [1, 2, 3],
        ...         "col2": ["A", "A", "B"]
        ...     }),
        ...     path="s3://bucket/prefix",
        ...     partition_cols=["col2"]
        ... )

        """
        return self._writer_factory(file_writer=self._write_parquet_file,
                                    df=df,
                                    path=path,
                                    filename=filename,
                                    partition_cols=partition_cols,
                                    num_files=num_files,
                                    mode=mode,
                                    parallel=parallel,
                                    self_destruct=self_destruct,
                                    **pd_kwargs)

    def _write_parquet_file(self,
                            df: pd.DataFrame,
                            path: str,
                            cpus: int,
                            filename: Optional[str] = None,
                            self_destruct: bool = False,
                            compression: Optional[str] = "snappy",
                            **pd_kwargs) -> str:
        preserve_index: bool = False
        if "preserve_index" in pd_kwargs:
            preserve_index = pd_kwargs["preserve_index"]
            del pd_kwargs["preserve_index"]
        if compression is None:
            compression_ext: str = ""
        elif compression == "snappy":
            compression_ext = ".snappy"
        elif compression == "gzip":
            compression_ext = ".gz"
        else:
            raise InvalidCompression(f"{compression} is invalid, please use snappy or gzip.")  # pragma: no cover
        file_path: str = f"{path}{uuid4().hex}{compression_ext}.parquet" if filename is None else f"{path}{filename}"
        table: pa.Table = pa.Table.from_pandas(df=df, nthreads=cpus, preserve_index=preserve_index, safe=False)
        if self_destruct is True:
            df.drop(df.index, inplace=True)
            del df
        file_obj: BytesIO = BytesIO()
        pq.write_table(table=table,
                       where=file_obj,
                       coerce_timestamps="ms",
                       compression=compression,
                       flavor="spark",
                       **pd_kwargs)
        del table
        file_obj.seek(0)
        _utils.upload_fileobj(s3_client=self._session.s3_client, file_obj=file_obj, path=file_path, cpus=cpus)
        return file_path

    def read_csv(self, path: str, parallel: bool = True, **pd_kwargs) -> pd.DataFrame:
        """Read CSV file from Amazon S3 to Pandas DataFrame.

        Note
        ----
        In case of `parallel=True` the number of process that will be spawned will be get from os.cpu_count().

        Parameters
        ----------
        path : str
            S3 path (e.g. s3://bucket/filename.csv).
        parallel : bool
            True to enable parallel requests, False to disable.
        pd_kwargs:
            keyword arguments forwarded to pandas.read_csv().
            https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.read_csv.html

        Returns
        -------
        pandas.DataFrame
            Pandas DataFrame.

        Examples
        --------
        >>> import awswrangler as wr
        >>> df = wr.s3.read_csv(path="s3://bucket/filename.csv")

        """
        return S3._read_csv(s3_client=self._session.s3_client, paths=[path], parallel=parallel, **pd_kwargs)[0]

    @staticmethod
    def _read_csv_remote(send_pipe: mp.connection.Connection,
                         session_primitives: "_SessionPrimitives",
                         paths: List[str],
                         parallel: bool = True,
                         **pd_kwargs) -> None:
        session: "Session" = session_primitives.build_session()
        s3_client: boto3.client = session.s3_client
        dfs: List[pd.DataFrame] = S3._read_csv(s3_client=s3_client, paths=paths, parallel=parallel, **pd_kwargs)
        send_pipe.send(dfs)
        send_pipe.close()

    @staticmethod
    def _read_csv(s3_client: "boto3.session.Session.client",
                  paths: List[str],
                  parallel: bool = True,
                  **pd_kwargs) -> List[pd.DataFrame]:
        cpus: int = _utils.get_cpu_count(parallel=parallel)
        dfs: List[pd.DataFrame] = []
        for path in paths:
            if pd_kwargs.get('compression', 'infer') == 'infer':
                pd_kwargs['compression'] = infer_compression(path, compression='infer')
            file_obj: BytesIO = _utils.download_fileobj(s3_client=s3_client, path=path, cpus=cpus)
            dfs.append(pd.read_csv(file_obj, **pd_kwargs))
        return dfs

    def read_parquet(self, path: str, parallel: bool = True, **pd_kwargs) -> pd.DataFrame:
        """Read Apache Parquet file from Amazon S3 to Pandas DataFrame.

        Note
        ----
        In case of `parallel=True` the number of process that will be spawned will be get from os.cpu_count().

        Parameters
        ----------
        path : str
            S3 path (e.g. s3://bucket/filename.parquet).
        parallel : bool
            True to enable parallel requests, False to disable.
        pd_kwargs:
            keyword arguments forwarded to pandas.read_parquet().
            https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.read_parquet.html

        Returns
        -------
        pandas.DataFrame
            Pandas DataFrame.

        Examples
        --------
        >>> import awswrangler as wr
        >>> df = wr.s3.read_parquet(path="s3://bucket/filename.parquet")

        """
        return S3._read_parquet(s3_client=self._session.s3_client, paths=[path], parallel=parallel, **pd_kwargs)[0]

    @staticmethod
    def _read_parquet_remote(send_pipe: mp.connection.Connection,
                             session_primitives: "_SessionPrimitives",
                             paths: List[str],
                             parallel: bool = True,
                             **pd_kwargs) -> None:
        session: "Session" = session_primitives.build_session()
        s3_client: boto3.client = session.s3_client
        dfs: List[pd.DataFrame] = S3._read_parquet(s3_client=s3_client, paths=paths, parallel=parallel, **pd_kwargs)
        send_pipe.send(dfs)
        send_pipe.close()

    @staticmethod
    def _read_parquet(s3_client: "boto3.session.Session.client",
                      paths: List[str],
                      parallel: bool = True,
                      **pd_kwargs) -> List[pd.DataFrame]:
        cpus: int = _utils.get_cpu_count(parallel=parallel)
        use_threads: bool = True if cpus > 1 else False
        pd_kwargs["use_threads"] = use_threads
        dfs: List[pd.DataFrame] = []
        for path in paths:
            file_obj: BytesIO = _utils.download_fileobj(s3_client=s3_client, path=path, cpus=cpus)
            table: pa.Table = pq.read_table(source=file_obj, **pd_kwargs)
            file_obj.seek(0)
            file_obj.truncate(0)
            file_obj.close()
            del file_obj
            dfs.append(
                table.to_pandas(use_threads=use_threads,
                                split_blocks=True,
                                self_destruct=True,
                                integer_object_nulls=False))
        return dfs

    def _read_list_factory(self, file_reader: Callable, file_reader_remote: Callable, paths: List[str], parallel: bool,
                           chunked: bool, **pd_kwargs) -> Union[pd.DataFrame, Iterator[pd.DataFrame]]:
        if parallel is False and chunked is True:
            return self._read_list_iterator(file_reader=file_reader, paths=paths, parallel=parallel, **pd_kwargs)
        elif parallel is False:
            dfs: List[pd.DataFrame] = file_reader(s3_client=self._session.s3_client,
                                                  paths=paths,
                                                  parallel=parallel,
                                                  **pd_kwargs)
        else:
            dfs_list = _utils.parallelize(func=file_reader_remote,
                                          session=self._session,
                                          lst=paths,
                                          has_return=True,
                                          **pd_kwargs)
            dfs = [item for sublist in dfs_list for item in sublist]
        logger.debug(f"Concatenating all {len(paths)} DataFrames...")
        df: pd.DataFrame = pd.concat(objs=dfs, ignore_index=True, sort=False)
        logger.debug("Concatenation done!")
        return df

    def _read_list_iterator(self, file_reader: Callable, paths: List[str], parallel: bool,
                            **pd_kwargs) -> Iterator[pd.DataFrame]:
        for path in paths:
            yield file_reader(s3_client=self._session.s3_client, paths=[path], parallel=parallel, **pd_kwargs)[0]

    def read_csv_list(self,
                      paths: List[str],
                      parallel: bool = True,
                      chunked: bool = False,
                      **pd_kwargs) -> Union[pd.DataFrame, Iterator[pd.DataFrame]]:
        """Read all CSV files in the list and return a single concatenated Pandas DataFrame.

        Note
        ----
        In case of `parallel=True` the number of process that will be spawned will be get from os.cpu_count().

        Parameters
        ----------
        paths : str
            S3 path (e.g. s3://bucket/filename.csv).
        parallel : bool
            True to enable parallel operations, False to disable.
        chunked: bool
            Nice for environments with memory restrictions. Return a generator of DataFrames, a DataFrame per file. Takes no effect if `parallel=True`.
        pd_kwargs:
            keyword arguments forwarded to pandas.read_csv().
            https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.read_csv.html

        Returns
        -------
        Union[pd.DataFrame, Iterator[pd.DataFrame]]
            A single Pandas DataFrame if `chunked=False`. A generator of DataFrames if `chunked=True`.

        Examples
        --------
        >>> import awswrangler as wr
        >>> df = wr.s3.read_csv_list(paths=["s3://bucket/filename1.csv", "s3://bucket/filename2.csv"])

        """
        return self._read_list_factory(file_reader=self._read_csv,
                                       file_reader_remote=self._read_csv_remote,
                                       paths=paths,
                                       parallel=parallel,
                                       chunked=chunked,
                                       **pd_kwargs)

    def read_parquet_list(self,
                          paths: List[str],
                          parallel: bool = True,
                          chunked: bool = False,
                          **pd_kwargs) -> Union[pd.DataFrame, Iterator[pd.DataFrame]]:
        """Read all parquet files in the list and return a single concatenated Pandas DataFrame.

        Note
        ----
        In case of `parallel=True` the number of process that will be spawned will be get from os.cpu_count().

        Parameters
        ----------
        paths : str
            S3 path (e.g. s3://bucket/filename.parquet).
        parallel : bool
            True to enable parallel operations, False to disable.
        chunked: bool
            Nice for environments with memory restrictions. Return a generator of DataFrames, a DataFrame per file. Takes no effect if `parallel=True`.
        pd_kwargs:
            keyword arguments forwarded to pandas.read_parquet().
            https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.read_parquet.html

        Returns
        -------
        Union[pd.DataFrame, Iterator[pd.DataFrame]]
            A single Pandas DataFrame if `chunked=False`. A generator of DataFrames if `chunked=True`.

        Examples
        --------
        >>> import awswrangler as wr
        >>> df = wr.s3.read_parquet_list(paths=["s3://bucket/filename1.parquet", "s3://bucket/filename2.parquet"])

        """
        return self._read_list_factory(file_reader=self._read_parquet,
                                       file_reader_remote=self._read_parquet_remote,
                                       paths=paths,
                                       parallel=parallel,
                                       chunked=chunked,
                                       **pd_kwargs)
