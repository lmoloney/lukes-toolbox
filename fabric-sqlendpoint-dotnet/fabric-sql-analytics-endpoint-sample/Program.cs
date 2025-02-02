using Microsoft.Data.SqlClient;
using Azure.Identity;
using Azure.Core;
using System.Data;
// dont forget to add the nuget packages...

//NOTE you need to set the following environment variables
//AZURE_CLIENT_ID
//AZURE_CLIENT_SECRET
//AZURE_TENANT_ID
//obvs you can use MI if you run on Azure service that supports it :)


var  DefaultAzureCredentialOptions  =  new DefaultAzureCredentialOptions 
    {
        ExcludeAzureCliCredential = true,
        ExcludeManagedIdentityCredential = true,
        ExcludeSharedTokenCacheCredential = true,
        ExcludeVisualStudioCredential = true,
        ExcludeAzurePowerShellCredential = true,
        ExcludeEnvironmentCredential = false,
        ExcludeVisualStudioCodeCredential = true,
        ExcludeInteractiveBrowserCredential = true
    };

    
    //set this connection strong to whatever you want
    var sqlServer = "tenantshort-workspaceshort.datawarehouse.pbidedicated.windows.net";
    //ditto with the database
    var sqlDatabase = "wwilakehouse";

    var accessToken = new DefaultAzureCredential(DefaultAzureCredentialOptions).GetToken(new TokenRequestContext(new string[] { "https://database.windows.net//.default" }));
    var connectionString = $"Server={sqlServer};Database={sqlDatabase};ApplicationIntent=ReadOnly";

    //Set AAD Access Token, Open Conneciton, Run Queries and Disconnect
    using var con = new SqlConnection(connectionString);
    con.AccessToken = accessToken.Token;
    con.Open();
    using var cmd = new SqlCommand();
    cmd.Connection = con;
    cmd.CommandType = CommandType.Text;
    //change this query to any query you want to run
    cmd.CommandText = "SELECT TABLE_NAME FROM wwilakehouse.INFORMATION_SCHEMA.TABLES";
    var res =cmd.ExecuteScalar();
    con.Close();

  Console.WriteLine(res);