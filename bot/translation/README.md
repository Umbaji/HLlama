
Google Cloud Translation authenticates with a service account of your own Google Cloud project:

`gcloud auth activate-service-account <service-account>@<project>.iam.gserviceaccount.com --key-file=/path/to/<service-account-key>.json --project="<project>"`

The key file stays outside the repository.
