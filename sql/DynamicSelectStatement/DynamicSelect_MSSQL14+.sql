select stringagg(concat('[',column_name,'] as [',replace(column_name,' ','_'), ']'), ', ') as SelectStatement
from INFORMATION_SCHEMA.COLUMNS
where DATA_TYPE not in ('geography','varbinary')
and TABLE_SCHEMA = '<<SCHEMA NAME>>'
and TABLE_NAME = '<<TABLE NAME>>'