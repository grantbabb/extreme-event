#!/bin/bash
# delete-stack.sh

set -e

STACK_NAME="city-coordinates-agent-stack"
REGION="us-west-2"

echo "WARNING: This will delete the entire stack including:"
echo "  - Bedrock Agent"
echo "  - Lambda Function"
echo "  - S3 Bucket (must be empty)"
echo "  - All IAM roles and policies"
echo ""
read -p "Are you sure? (type 'yes' to confirm): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Deletion cancelled"
    exit 0
fi

# Get S3 bucket name and empty it
BUCKET_NAME=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`OpenAPIBucketName`].OutputValue' \
    --output text 2>/dev/null || echo "")

if [ ! -z "$BUCKET_NAME" ]; then
    echo "Emptying S3 bucket: $BUCKET_NAME"
    aws s3 rm s3://$BUCKET_NAME --recursive --region $REGION 2>/dev/null || true
fi

echo "Deleting CloudFormation stack..."
aws cloudformation delete-stack \
    --stack-name $STACK_NAME \
    --region $REGION

echo "Waiting for stack deletion to complete..."
aws cloudformation wait stack-delete-complete \
    --stack-name $STACK_NAME \
    --region $REGION

echo "Stack deleted successfully!"