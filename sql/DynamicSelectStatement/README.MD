# Dynamic Select Statement

NOTE - README in progress.

Currently only supports Microsoft SQL Server

## Basics
These scripts return the select part of a SQL script based on certain parameters that can then be used be passed to another services to interact with.

There are (currently) two scripts in this directory

1. DynamicSelect_MSSQL14+.sql - this is a bit simpler to work with and understand, but it is only compatible with Databases running SQL Server 14 / SQL Server 2017 or later.
2. DynamicSelect_MSSQL_ALL.sql - this is a bit more complex to work with, but it is compatible with all version of SQL Server which are currently supported.

NOTE: DynamicSelect_MSSQL_ALL.sql was heavily inspired by https://social.msdn.microsoft.com/Forums/sqlserver/en-US/63bd1c26-059c-40f7-9feb-9b41bc94848e/need-to-use-dynamic-column-names-in-select-statement-of-any-tables?forum=transactsql&utm_source=pocket_saves on MSDN.

## Note about this README

These scripts are designed primarily when using Azure Data Factory or Synapse Pipelines to copy data from a source SQL Server, but can be used for any other purpose as needed. This readme focuses on using these scripts with Azure Data Factory or Synapse Pipelines.

## How these scripts work

Common elements to both scripts:

* Both scripts use INFORMATION_SCHEMA.COLUMNS to query column information
* Both scripts generate a statement that looks something like this

        

* Both scripts use REPLACE and CONCAT to
* Both scripts require you to provide a single table (and it's schema name) to provide a single output
* Both scripts also allow you to filter out column names where the SQL Data Type may be undesirable. The scripts are currently configured to remove the data types 'geography' and 'varbinary'

## How to use these with Azure Data Factory / Synapse Pipelines

When copying data from a SQL

select stringagg(concat('[',replace(COLUMN_NAME,' ','_'),']'), ', ') as SelectStatement
--REPLACE - Replaces spaces due to ADF/Parquet inablity to handle spaces in column names
--CONCAT - puts  square brackets [] around column name to deal with certain scenarios e.g. column called case.
--ST
from INFORMATION_SCHEMA.COLUMNS
where DATA_TYPE not in ('geography','varbinary')

and TABLE_SCHEMA = 'dbo'
and TABLE_NAME = 'test_data'
--order by ORDINAL_POSITION
