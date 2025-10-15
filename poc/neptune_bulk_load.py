import os
import time
import json
import boto3
import requests
from typing import List, Optional
from boto3 import Session
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from requests_auth_aws_sigv4 import AWSSigV4
# If your Neptune cluster uses a self-signed cert, you may set VERIFY_TLS=False.
# Prefer providing a proper CA bundle path via VERIFY_TLS=str(path_to_cabundle) in production.
VERIFY_TLS: Optional[bool | str] = True  # or False or "/path/to/ca-bundle.pem"


def upload_csvs_to_s3(bucket: str, prefix: str, local_files: List[str], region: str) -> None:
    s3 = boto3.client("s3", region_name=region)
    for local_path in local_files:
        key = f"{prefix.rstrip('/')}/{os.path.basename(local_path)}"
        print(f"Uploading {local_path} -> s3://{bucket}/{key}")
        s3.upload_file(local_path, bucket, key)


def start_bulk_load(
    neptune_endpoint: str,
    port: int,
    s3_bucket: str,
    s3_prefix: str,
    iam_role_arn: str,
    region: str,
    user_provided_edge_ids: bool = True,
    parallelism: str = "LOW",
    fail_on_error: bool = False,
    edge_only_load: bool = False,
    queue_request: bool = True,
) -> str:
    credentials = Session().get_credentials()
    if credentials is None:
        raise Exception("No AWS credentials found")
    creds = credentials.get_frozen_credentials()
    service = 'neptune-db'
    # conn_string = 'wss://' + neptune_endpoint + ':8182/gremlin'
    # region set inside config profile 
    # or via AWS_DEFAULT_REGION environment variable will be loaded
    region = Session().region_name if Session().region_name else region
    url = f"https://{neptune_endpoint}:{port}/loader"
    source = f"s3://{s3_bucket}/{s3_prefix.strip('/')}/"

    payload = {
        "source": source,
        "format": "csv",  # Neptune CSV (nodes/edges)
        "iamRoleArn": iam_role_arn,
        "region": region,
        "failOnError": fail_on_error,
        "parallelism": parallelism,
        "queueRequest": queue_request,
        # Set to True if your edge CSV has ~id; otherwise False to auto-generate
        # "userProvidedEdgeIds": user_provided_edge_ids,
        "edgeOnlyLoad": edge_only_load,
        # Optional parser tweaks:
        # "parserConfiguration": {"ignoreEmptyStrings": True, "allowNull": True}
    }
    print(f"Starting bulk load from {source}")
    print(payload)
    #request = AWSRequest(method='GET', url=url, data=None)
    #SigV4Auth(creds, service, region).add_auth(request)
    #aws_auth = AWSSigV4(service, region=region)
    #headers = dict([(x,request.headers[x]) for x in request.headers])
    #print("request:", aws_auth)
    # headers = {'Authorization': request.headers["Authorization"],
    #           'X-Amz-Security-Token': request.headers["X-Amz-Security-Token"]}
    # print(headers)
    resp = requests.post(url, 
                         json=payload, 
                         timeout=120, 
                         verify=VERIFY_TLS,
                         # auth=aws_auth
                         # headers=headers
                        )
    #print(creds)
    #resp.raise_for_status()
    data = resp.json()
    load_id = data.get("payload", {}).get("loadId")
    if not load_id:
        raise RuntimeError(f"Bulk load start did not return loadId: {json.dumps(data, indent=2)}")
    print(f"Bulk load started. loadId={load_id}")
    return load_id


def poll_bulk_load(neptune_endpoint: str, port: int, load_id: str, 
                   poll_seconds: int = 10) -> dict:
    url = f"https://{neptune_endpoint}:{port}/loader/{load_id}"
    terminal = {"LOAD_COMPLETED", "LOAD_FAILED", "LOAD_CANCELLED"}
    while True:
        resp = requests.get(url, timeout=30, verify=VERIFY_TLS)
        resp.raise_for_status()
        data = resp.json()
        overall = data.get("payload", {}).get("overallStatus", {})
        status = overall.get("status") or overall.get("overallStatus")  
        # some versions use 'status'
        progress = overall.get("totalRecords") or overall.get("totalTimeSpent")
        print(f"Status: {status} | Progress: {progress}")
        if status in terminal:
            return data
        time.sleep(poll_seconds)


def main():
    # ---- Fill these in ----
    AWS_REGION = os.environ.get("AWS_REGION", "us-west-2")
    S3_BUCKET = os.environ["S3_BUCKET"]                 # e.g., "my-neptune-load-bucket"
    S3_PREFIX = os.environ.get("S3_PREFIX", "neptune-load-demo")  # folder to load
    # role with S3 read perms and Neptune load perms
    IAM_ROLE_ARN = os.environ["IAM_ROLE_ARN"]           
    # e.g., "your-cluster.cluster-xxxx.us-east-1.neptune.amazonaws.com"
    NEPTUNE_ENDPOINT = os.environ["NEPTUNE_ENDPOINT"]
    NEPTUNE_PORT = int(os.environ.get("NEPTUNE_PORT", "8182"))
    # LOCAL_NODE_FILE = os.environ.get("LOCAL_NODE_FILE", "nodes.csv")
    LOCAL_EDGE_FILE = os.environ.get("LOCAL_EDGE_FILE", 
                                     "../data/datasets/roads/edges.csv")
    # ------------------------

    # 1) Upload CSVs to S3
    upload_csvs_to_s3(
        bucket=S3_BUCKET,
        prefix=S3_PREFIX,
        local_files=[LOCAL_EDGE_FILE], #LOCAL_NODE_FILE 
        region=AWS_REGION,
    )

    # 2) Start bulk load (point to the S3 prefix)
    load_id = start_bulk_load(
        neptune_endpoint=NEPTUNE_ENDPOINT,
        port=NEPTUNE_PORT,
        s3_bucket=S3_BUCKET,
        s3_prefix=S3_PREFIX,
        iam_role_arn=IAM_ROLE_ARN,
        region=AWS_REGION,
        user_provided_edge_ids=False,   # set False if your edges don't have ~id
        parallelism="MEDIUM",
        fail_on_error="TRUE",
        edge_only_load="TRUE",
        queue_request=True,
    )

    # 3) Poll for completion
    final = poll_bulk_load(NEPTUNE_ENDPOINT, NEPTUNE_PORT, load_id, poll_seconds=10)
    print(json.dumps(final, indent=2))

if __name__ == "__main__":
    # If you must disable TLS verification (not recommended), set VERIFY_TLS=False above.
    # Also consider:
    #   import urllib3
    #   urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    main()