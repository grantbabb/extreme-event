# Makefile

.PHONY: help deploy update delete test validate package clean

STACK_NAME := city-coordinates-agent-stack
REGION := us-east-1

help:
	@echo "Available commands:"
	@echo "  make deploy    - Deploy the CloudFormation stack"
	@echo "  make update    - Update existing stack"
	@echo "  make delete    - Delete the stack"
	@echo "  make test      - Run test suite"
	@echo "  make validate  - Validate CloudFormation template"
	@echo "  make package   - Create Lambda deployment package"
	@echo "  make clean     - Clean up temporary files"
	@echo "  make status    - Show stack status"
	@echo "  make outputs   - Show stack outputs"
	@echo "  make events    - Show recent stack events"

deploy:
	@chmod +x deploy.sh
	@./deploy.sh

update:
	@chmod +x update-stack.sh
	@./update-stack.sh

delete:
	@chmod +x delete-stack.sh
	@./delete-stack.sh

test:
	@AGENT_ID=$$(aws cloudformation describe-stacks \
		--stack-name $(STACK_NAME) \
		--region $(REGION) \
		--query 'Stacks[0].Outputs[?OutputKey==`AgentId`].OutputValue' \
		--output text); \
	ALIAS_ID=$$(aws cloudformation describe-stacks \
		--stack-name $(STACK_NAME) \
		--region $(REGION) \
		--query 'Stacks[0].Outputs[?OutputKey==`AgentAliasId`].OutputValue' \
		--output text); \
	python test_agent.py --agent-id $$AGENT_ID --alias-id $$ALIAS_ID --region $(REGION) --suite

validate:
	@aws cloudformation validate-template \
		--template-body file://cloudformation-template.yaml \
		--region $(REGION)
	@echo "Template is valid!"

package:
	@echo "Creating Lambda deployment package..."
	@mkdir -p lambda-package
	@cp lambda_function.py lambda-package/
	@cd lambda-package && pip install requests -t . --quiet
	@cd lambda-package && zip -r ../lambda-deployment.zip . > /dev/null
	@rm -rf lambda-package
	@echo "Package created: lambda-deployment.zip"

clean:
	@rm -rf lambda-package lambda-deployment.zip parameters.json
	@echo "Cleaned up temporary files"

status:
	@aws cloudformation describe-stacks \
		--stack-name $(STACK_NAME) \
		--region $(REGION) \
		--query 'Stacks[0].StackStatus' \
		--output text

outputs:
	@aws cloudformation describe-stacks \
		--stack-name $(STACK_NAME) \
		--region $(REGION) \
		--query 'Stacks[0].Outputs' \
		--output table

events:
	@aws cloudformation describe-stack-events \
		--stack-name $(STACK_NAME) \
		--region $(REGION) \
		--max-items 20 \
		--output table