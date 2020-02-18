/*
Creates or alters stored procedure which creates a schema name if it doesn't exist
Pass in the schema name
N.B. does not allow changing the DB, something to do in the future.
*/

create or ALTER PROC [dbo].[CreateSchema] @SchemaName [varchar](50) AS
	declare @CreateSchemaSQLStatement varchar(200)
	set @CreateSchemaSQLStatement='CREATE SCHEMA ['+ @SchemaName + ']'
	
	IF NOT EXISTS (
	SELECT  schema_name
	FROM    information_schema.schemata
	WHERE   schema_name = @SchemaName )
	BEGIN
	execute(@CreateSchemaSQLStatement)
	END
