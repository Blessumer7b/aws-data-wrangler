![AWS Data Wrangler](docs/source/_static/logo.png?raw=true "AWS Data Wrangler")

> Pandas on AWS

[![Release](https://img.shields.io/badge/release-1.0.0-brightgreen.svg)](https://pypi.org/project/awswrangler/)
[![Python Version](https://img.shields.io/badge/python-3.6%20%7C%203.7%20%7C%203.8-brightgreen.svg)](https://anaconda.org/conda-forge/awswrangler)
[![Documentation Status](https://readthedocs.org/projects/aws-data-wrangler/badge/?version=latest)](https://aws-data-wrangler.readthedocs.io/?badge=latest)
[![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen.svg)](https://pypi.org/project/awswrangler/)
[![Average time to resolve an issue](http://isitmaintained.com/badge/resolution/awslabs/aws-data-wrangler.svg)](http://isitmaintained.com/project/awslabs/aws-data-wrangler "Average time to resolve an issue")
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

**PyPI**: [![PyPI Downloads](https://img.shields.io/pypi/dm/awswrangler.svg)](https://pypi.org/project/awswrangler/)

**Conda**: [![Conda Downloads](https://img.shields.io/conda/dn/conda-forge/awswrangler.svg)](https://anaconda.org/conda-forge/awswrangler)

## Resources
- [Read the Docs](https://aws-data-wrangler.readthedocs.io)
- [Use Cases](#Use-Cases)
  - [Pandas](#Pandas)
  - [PySpark](#PySpark)
  - [General](#General)
- [Install](https://aws-data-wrangler.readthedocs.io/install.html)
- [Examples](https://aws-data-wrangler.readthedocs.io/examples.html)
- [Tutorials](https://aws-data-wrangler.readthedocs.io/tutorials.html)
- [API Reference](https://aws-data-wrangler.readthedocs.io/api/awswrangler.html)
- [License](https://aws-data-wrangler.readthedocs.io/license.html)
- [Contributing](https://aws-data-wrangler.readthedocs.io/contributing.html)

## Use Cases

### Pandas

| FROM                     | TO              | Features                                                                                                                                                                                                                           |
|--------------------------|-----------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Pandas DataFrame         | Amazon S3       | Parquet, CSV, Partitions, Parallelism, Overwrite/Append/Partitions-Upsert modes,<br>KMS Encryption, Glue Metadata (Athena, Spectrum, Spark, Hive, Presto)                                                                          |
| Amazon S3                | Pandas DataFrame| Parquet (Pushdown filters), CSV, Fixed-width formatted, Partitions, Parallelism,<br>KMS Encryption, Multiple files                                                                                                                                        |
| Amazon Athena            | Pandas DataFrame| Workgroups, S3 output path, Encryption, and two different engines:<br><br>- ctas_approach=False **->** Batching and restrict memory environments<br>- ctas_approach=True  **->** Blazing fast, parallelism and enhanced data types |
| Pandas DataFrame         | Amazon Redshift | Blazing fast using parallel parquet on S3 behind the scenes<br>Append/Overwrite/Upsert modes                                                                                                                                       |
| Amazon Redshift          | Pandas DataFrame| Blazing fast using parallel parquet on S3 behind the scenes                                                                                                                                                                        |
| Pandas DataFrame         | Amazon Aurora   | Supported engines: MySQL, PostgreSQL<br>Blazing fast using parallel CSV on S3 behind the scenes<br>Append/Overwrite modes                                                                                                          |
| Amazon Aurora            | Pandas DataFrame| Supported engines: MySQL<br>Blazing fast using parallel CSV on S3 behind the scenes                                                                                                                                                |
| CloudWatch Logs Insights | Pandas DataFrame| Query results                                                                                                                                                                                                                      |
| Glue Catalog             | Pandas DataFrame| List and get Tables details. Good fit with Jupyter Notebooks.                                                                                                                                                                      |

### General

| Feature                                     | Details                             |
|---------------------------------------------|-------------------------------------|
| List S3 objects                             | e.g. wr.s3.list_objects("s3://...") |
| Delete S3 objects                           | Parallel                            |
| Delete listed S3 objects                    | Parallel                            |
| Delete NOT listed S3 objects                | Parallel                            |
| Copy listed S3 objects                      | Parallel                            |
| Get the size of S3 objects                  | Parallel                            |
| Get CloudWatch Logs Insights query results  |                                     |
| Load partitions on Athena/Glue table        | Through "MSCK REPAIR TABLE"         |
| Create EMR cluster                          | "For humans"                        |
| Terminate EMR cluster                       | "For humans"                        |
| Get EMR cluster state                       | "For humans"                        |
| Submit EMR step(s)                          | "For humans"                        |
| Get EMR step state                          | "For humans"                        |
| Query Athena to receive python primitives   | Returns *Iterable[Dict[str, Any]*   |
| Load and Unzip SageMaker jobs outputs       |                                     |
| Dump Amazon Redshift as Parquet files on S3 |                                     |
| Dump Amazon Aurora as CSV files on S3       | Only for MySQL engine               |
