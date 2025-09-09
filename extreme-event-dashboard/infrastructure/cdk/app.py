import aws_cdk as cdk
from aws_cdk import Stack
from constructs import Construct


class ExtremeEventStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        # TODO: add S3 for frontend, API Gateway + Lambda for API, S3 for videos


app = cdk.App()
ExtremeEventStack(app, "ExtremeEventStack")
app.synth()
