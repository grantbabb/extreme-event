#!/bin/bash
# deploy.sh

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

STACK_NAME="city-coordinates-agent-stack"
REGION="us-west-2"
TEMPLATE_FILE="bedrock-agent.yaml"
PARAMETERS_FILE="parameters.json"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Bedrock Agent CloudFormation Deploy${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"

if ! command -v aws &> /dev/null; then
    echo -e "${RED}Error: AWS CLI is not installed${NC}"
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is not installed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Prerequisites met${NC}\n"

# Get API keys
echo -e "${YELLOW}API Key Configuration${NC}"
echo "Note: You can skip this and use Nominatim (free, no key required)"
echo ""

read -p "Enter OpenCage API key (or press Enter to skip): " OPENCAGE_KEY
read -p "Enter Google Maps API key (or press Enter to skip): " GOOGLE_KEY

# Choose provider
echo -e "\n${YELLOW}Available providers:${NC}"
echo "1) opencage  - Free tier: 2,500 requests/day"
echo "2) google    - Paid: \$5 per 1000 requests"
echo "3) nominatim - Free, 1 req/sec limit, no key needed"
read -p "Choose provider (1-3) [3]: " PROVIDER_CHOICE

case $PROVIDER_CHOICE in
    1) PROVIDER="opencage" ;;
    2) PROVIDER="google" ;;
    *) PROVIDER="nominatim" ;;
esac

echo -e "${GREEN}Selected provider: $PROVIDER${NC}\n"

# Create parameters file
cat > $PARAMETERS_FILE <<EOF
[
  {
    "ParameterKey": "AgentName",
    "ParameterValue": "city-coordinates-agent"
  },
  {
    "ParameterKey": "GeocodingProvider",
    "ParameterValue": "$PROVIDER"
  },
  {
    "ParameterKey": "OpenCageApiKey",
    "ParameterValue": "$OPENCAGE_KEY"
  },
  {
    "ParameterKey": "GoogleMapsApiKey",
    "ParameterValue": "$GOOGLE_KEY"
  },
  {
    "ParameterKey": "LambdaTimeout",
    "ParameterValue": "30"
  },
  {
    "ParameterKey": "LambdaMemorySize",
    "ParameterValue": "256"
  },
  {
    "ParameterKey": "LogRetentionDays",
    "ParameterValue": "14"
  },
  {
    "ParameterKey": "ClaudeModelId",
    "ParameterValue": "anthropic.claude-3-5-sonnet-20241022-v2:0"
  },
  {
    "ParameterKey": "Environment",
    "ParameterValue": "production"
  }
]
EOF

echo -e "${GREEN}✓ Parameters file created${NC}\n"

# Get AWS Account ID for S3 bucket name
echo -e "${YELLOW}Getting AWS Account ID...${NC}"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --region $REGION)
echo -e "${GREEN}Account ID: $AWS_ACCOUNT_ID${NC}"

# Get AgentName from parameters file
AGENT_NAME=$(cat $PARAMETERS_FILE | grep -A 1 '"ParameterKey": "AgentName"' | grep "ParameterValue" | cut -d'"' -f4)
S3_BUCKET_NAME="${AGENT_NAME}-openapi-${AWS_ACCOUNT_ID}"

echo -e "${YELLOW}S3 Bucket for schema: $S3_BUCKET_NAME${NC}"

# Upload OpenAPI schema to S3
echo -e "${GREEN}Uploading OpenAPI schema to S3...${NC}"
aws s3 cp $OPENAPI_SCHEMA_FILE s3://$S3_BUCKET_NAME/openapi_schema.yaml --region $REGION

if [ $? -eq 0 ]; then
    echo -e "${GREEN}OpenAPI schema uploaded successfully to s3://$S3_BUCKET_NAME/openapi_schema.yaml${NC}"
else
    echo -e "${RED}Failed to upload OpenAPI schema${NC}"
    exit 1
fi

# Prepare Lambda deployment package
echo -e "${YELLOW}Creating Lambda deployment package...${NC}"

mkdir -p lambda-package
cp lambda_function.py lambda-package/

# Install dependencies
cd lambda-package
pip install requests -t . --quiet
zip -r ../lambda-deployment.zip . > /dev/null
cd ..

echo -e "${GREEN}✓ Lambda package created${NC}\n"

# Validate CloudFormation template
echo -e "${GREEN}✓ Region is $REGION\n"

echo -e "${YELLOW}Validating CloudFormation template...${NC}"
aws cloudformation validate-template \
    --template-body file://$TEMPLATE_FILE \
    --region $REGION > /dev/null

echo -e "${GREEN}✓ Template is valid${NC}\n"

# Check if stack exists
if aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION &> /dev/null; then
    echo -e "${YELLOW}Stack exists. Updating...${NC}"
    OPERATION="update"
    
    aws cloudformation update-stack \
        --stack-name $STACK_NAME \
        --template-body file://$TEMPLATE_FILE \
        --parameters file://$PARAMETERS_FILE \
        --capabilities CAPABILITY_NAMED_IAM \
        --region $REGION
else
    echo -e "${YELLOW}Creating new stack...${NC}"
    OPERATION="create"
    
    aws cloudformation create-stack \
        --stack-name $STACK_NAME \
        --template-body file://$TEMPLATE_FILE \
        --parameters file://$PARAMETERS_FILE \
        --capabilities CAPABILITY_NAMED_IAM \
        --region $REGION
fi

echo -e "${BLUE}Waiting for stack $OPERATION to complete...${NC}"
echo "This may take 5-10 minutes..."

aws cloudformation wait stack-${OPERATION}-complete \
    --stack-name $STACK_NAME \
    --region $REGION

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Stack $OPERATION completed successfully${NC}\n"
else
    echo -e "${RED}✗ Stack $OPERATION failed${NC}"
    aws cloudformation describe-stack-events \
        --stack-name $STACK_NAME \
        --region $REGION \
        --max-items 10
    exit 1
fi

# Get outputs
echo -e "${YELLOW}Retrieving stack outputs...${NC}\n"

AGENT_ID=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`AgentId`].OutputValue' \
    --output text)

ALIAS_ID=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`AgentAliasId`].OutputValue' \
    --output text)

LAMBDA_NAME=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`LambdaFunctionName`].OutputValue' \
    --output text)

BUCKET_NAME=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`OpenAPIBucketName`].OutputValue' \
    --output text)

# Upload OpenAPI schema to S3
echo -e "${YELLOW}Uploading OpenAPI schema to S3...${NC}"
aws s3 cp openapi_schema.yaml s3://$BUCKET_NAME/ --region $REGION
echo -e "${GREEN}✓ OpenAPI schema uploaded${NC}\n"

# Update Lambda function code
echo -e "${YELLOW}Updating Lambda function code...${NC}"
aws lambda update-function-code \
    --function-name $LAMBDA_NAME \
    --zip-file fileb://lambda-deployment.zip \
    --region $REGION > /dev/null

echo -e "${GREEN}✓ Lambda code updated${NC}\n"

# Wait for Lambda to be ready
echo -e "${YELLOW}Waiting for Lambda function to be ready...${NC}"
aws lambda wait function-updated \
    --function-name $LAMBDA_NAME \
    --region $REGION

echo -e "${GREEN}✓ Lambda function ready${NC}\n"

# Display summary
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}       Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}\n"

echo -e "${BLUE}Stack Details:${NC}"
echo "  Stack Name:      $STACK_NAME"
echo "  Region:          $REGION"
echo "  Agent ID:        $AGENT_ID"
echo "  Alias ID:        $ALIAS_ID"
echo "  Lambda Function: $LAMBDA_NAME"
echo "  S3 Bucket:       $BUCKET_NAME"
echo ""

echo -e "${BLUE}Test Commands:${NC}"
echo "  # Run test suite"
echo "  python test_agent.py --agent-id $AGENT_ID --alias-id $ALIAS_ID --region $REGION --suite"
echo ""
echo "  # Interactive mode"
echo "  python test_agent.py --agent-id $AGENT_ID --alias-id $ALIAS_ID --region $REGION"
echo ""
echo "  # Single query"
echo "  python test_agent.py --agent-id $AGENT_ID --alias-id $ALIAS_ID --region $REGION --prompt 'What are coordinates of Tokyo?'"
echo ""

echo -e "${BLUE}Management Commands:${NC}"
echo "  # View stack events"
echo "  aws cloudformation describe-stack-events --stack-name $STACK_NAME --region $REGION"
echo ""
echo "  # View stack outputs"
echo "  aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION --query 'Stacks[0].Outputs'"
echo ""
echo "  # Delete stack"
echo "  aws cloudformation delete-stack --stack-name $STACK_NAME --region $REGION"
echo ""

# Offer to run tests
read -p "Run test suite now? (y/n): " RUN_TESTS
if [[ $RUN_TESTS =~ ^[Yy]$ ]]; then
    echo -e "\n${YELLOW}Running tests...${NC}\n"
    python test_agent.py \
        --agent-id $AGENT_ID \
        --alias-id $ALIAS_ID \
        --region $REGION \
        --suite
fi

# Cleanup
rm -rf lambda-package lambda-deployment.zip

echo -e "\n${GREEN}Done!${NC}"