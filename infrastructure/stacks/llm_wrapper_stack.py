"""Data-plane infra for the llm-wrapper library.

Provisions the Postgres database and secrets the library reads at runtime:
  - VPC (2 AZs, 1 NAT for cost)
  - RDS PostgreSQL 16 (pgcrypto enabled via init SQL, run after deploy)
  - Secrets Manager secret for CREDENTIAL_ENCRYPTION_KEY
  - Security group allowing Postgres access from within the VPC

Compute (Lambda / ECS / Batch) that consumes the library is intentionally
out of scope — add it in a separate stack per consumer.
"""
from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_rds as rds
from aws_cdk import aws_secretsmanager as sm
from constructs import Construct


class LlmWrapperStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        stage: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        is_prod = stage == "prod"

        vpc = ec2.Vpc(
            self,
            "Vpc",
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="isolated",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )

        encryption_key_secret = sm.Secret(
            self,
            "CredentialEncryptionKey",
            secret_name=f"llm-wrapper/{stage}/credential-encryption-key",
            description="Symmetric key used with pgcrypto for model_credentials",
            generate_secret_string=sm.SecretStringGenerator(
                password_length=48,
                exclude_punctuation=True,
                include_space=False,
            ),
            removal_policy=RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY,
        )

        db_sg = ec2.SecurityGroup(
            self,
            "DbSecurityGroup",
            vpc=vpc,
            description="llm-wrapper Postgres access",
            allow_all_outbound=False,
        )
        db_sg.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(5432),
            description="Postgres from within VPC",
        )

        db = rds.DatabaseInstance(
            self,
            "Postgres",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_16_3,
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.BURSTABLE4_GRAVITON,
                ec2.InstanceSize.MEDIUM if is_prod else ec2.InstanceSize.MICRO,
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
            ),
            security_groups=[db_sg],
            database_name="llm_wrapper",
            credentials=rds.Credentials.from_generated_secret(
                username="llm_wrapper",
                secret_name=f"llm-wrapper/{stage}/db-credentials",
            ),
            allocated_storage=20,
            max_allocated_storage=100 if is_prod else 50,
            storage_encrypted=True,
            multi_az=is_prod,
            backup_retention=Duration.days(14 if is_prod else 1),
            delete_automated_backups=not is_prod,
            deletion_protection=is_prod,
            removal_policy=RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY,
            parameter_group=rds.ParameterGroup(
                self,
                "PgParams",
                engine=rds.DatabaseInstanceEngine.postgres(
                    version=rds.PostgresEngineVersion.VER_16_3,
                ),
                parameters={
                    "shared_preload_libraries": "pg_stat_statements",
                    "log_min_duration_statement": "500",
                },
            ),
        )

        self.vpc = vpc
        self.db_security_group = db_sg
        self.db_secret = db.secret
        self.encryption_key_secret = encryption_key_secret

        CfnOutput(
            self,
            "DbEndpoint",
            value=db.db_instance_endpoint_address,
            description="Postgres host — compose into DATABASE_URL with the db-credentials secret",
        )
        CfnOutput(
            self,
            "DbSecretArn",
            value=db.secret.secret_arn if db.secret else "",
            description="Secrets Manager ARN for DB username/password",
        )
        CfnOutput(
            self,
            "CredentialEncryptionKeySecretArn",
            value=encryption_key_secret.secret_arn,
            description="Secrets Manager ARN for CREDENTIAL_ENCRYPTION_KEY",
        )
        CfnOutput(
            self,
            "VpcId",
            value=vpc.vpc_id,
            description="VPC ID for consumer stacks to import",
        )
        CfnOutput(
            self,
            "DbSecurityGroupId",
            value=db_sg.security_group_id,
            description="Attach consumers to this SG (or peer into it) to reach Postgres",
        )
