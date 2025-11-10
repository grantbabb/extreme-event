#!/bin/bash
# update-stack.sh

set -e

STACK_NAME="city-coordinates-agent-stack"
REGION="us-west-2"

echo "Updating CloudFormation stack..."

#aws cloudformation update-stack \
#    --stack-name $STACK_NAME \
#    --template-body file://bedrock-agent.yaml \
#    --parameters file://parameters.json \
#    --capabilities CAPABILITY_NAMED_IAM \
#    --region $REGION

# echo "Waiting for stack update to complete..."
# aws cloudformation wait stack-update-complete \
#    --stack-name $STACK_NAME \
#    --region $REGION

# echo "Stack updated successfully!"

# Get Lambda function name
LAMBDA_NAME=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`LambdaFunctionName`].OutputValue' \
    --output text)

# Prepare Lambda deployment package
echo -e "${YELLOW}Creating Lambda deployment package...${NC}"

mkdir -p lambda-package
cp lambda_function.py neptune_connection.py lambda-package/

# Install dependencies
cd lambda-package
pip install requests requests-auth-aws-sigv4 boto3 -t . --quiet
zip -r ../lambda-deployment.zip . > /dev/null
cd ..
echo -e "${GREEN}✓ Lambda package created${NC}\n"

# Update Lambda code if package exists
if [ -f "lambda-deployment.zip" ]; then
    echo "Updating Lambda function code..."
    aws lambda update-function-code \
        --function-name $LAMBDA_NAME \
        --zip-file fileb://lambda-deployment.zip \
        --region $REGION
    
    aws lambda wait function-updated \
        --function-name $LAMBDA_NAME \
        --region $REGION
    
    echo "Lambda function updated!"
fi