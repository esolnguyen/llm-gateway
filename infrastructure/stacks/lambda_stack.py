"""Container-image Lambda that exposes llm-wrapper behind an HTTP API.

Network:
  - Placed in private-with-egress subnets so it can reach Secrets Manager and
    LLM provider APIs via NAT.
  - Reaches RDS (in isolated subnets) through the VPC local route. The DB SG
    already permits 5432 from the VPC CIDR, so no extra ingress rule needed.
"""
from pathlib import Path

from aws_cdk import CfnOutput, Duration, Stack
from aws_cdk import aws_apigatewayv2 as apigw
from aws_cdk import aws_apigatewayv2_integrations as apigw_int
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_logs as logs
from aws_cdk import aws_secretsmanager as sm
from constructs import Construct

REPO_ROOT = Path(__file__).resolve().parents[2]


class LambdaStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        stage: str,
        vpc: ec2.IVpc,
        db_secret: sm.ISecret,
        encryption_key_secret: sm.ISecret,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        fn_sg = ec2.SecurityGroup(
            self,
            "FnSecurityGroup",
            vpc=vpc,
            description="llm-wrapper Lambda egress",
            allow_all_outbound=True,
        )

        fn = _lambda.DockerImageFunction(
            self,
            "LlmFunction",
            function_name=f"llm-wrapper-{stage}",
            code=_lambda.DockerImageCode.from_image_asset(
                directory=str(REPO_ROOT),
                file="infrastructure/lambda/Dockerfile",
            ),
            architecture=_lambda.Architecture.X86_64,
            memory_size=1024,
            timeout=Duration.seconds(60),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
            ),
            security_groups=[fn_sg],
            environment={
                "DB_SECRET_ARN": db_secret.secret_arn,
                "ENCRYPTION_KEY_SECRET_ARN": encryption_key_secret.secret_arn,
                "MODULE_NAME": "lambda",
                "SERVICE_NAME": "chat",
                "LOG_LEVEL": "INFO",
            },
            tracing=_lambda.Tracing.ACTIVE,
            log_retention=logs.RetentionDays.ONE_MONTH,
        )

        db_secret.grant_read(fn)
        encryption_key_secret.grant_read(fn)

        api = apigw.HttpApi(
            self,
            "HttpApi",
            api_name=f"llm-wrapper-{stage}",
        )
        api.add_routes(
            path="/llm",
            methods=[apigw.HttpMethod.POST],
            integration=apigw_int.HttpLambdaIntegration("LlmIntegration", fn),
        )

        CfnOutput(self, "ApiEndpoint", value=api.api_endpoint)
        CfnOutput(self, "FunctionName", value=fn.function_name)
