# Make scripts executable
chmod +x *.sh

# Deploy the stack
./deploy.sh

# Or use Makefile
make deploy

# Check stack status
make status

# View outputs
make outputs

# Run tests
make test

# Update stack after changes
make update

# View recent events
make events

# Delete stack
make delete