pip install -r requirements.txt
export AWS_REGION=us-west-2
export AWS_REGION=neptune-db
export S3_BUCKET=datasets-in-out
export S3_PREFIX=input/road-usa/
export IAM_ROLE_ARN=arn:aws:iam::063299843915:role/service-role/AWSNeptuneNotebookRole-NeptuneNbUser
export NEPTUNE_ENDPOINT=db-neptune-dev.cluster-criq8uemaejw.us-west-2.neptune.amazonaws.com"
python neptune_bulk_load.py