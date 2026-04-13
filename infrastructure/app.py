#!/usr/bin/env python3
import os

import aws_cdk as cdk

from stacks.lambda_stack import LambdaStack
from stacks.llm_wrapper_stack import LlmWrapperStack

app = cdk.App()

env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1"),
)

stage = app.node.try_get_context("stage") or "dev"

data = LlmWrapperStack(
    app,
    f"LlmWrapper-{stage}",
    stage=stage,
    env=env,
)

LambdaStack(
    app,
    f"LlmWrapperLambda-{stage}",
    stage=stage,
    vpc=data.vpc,
    db_secret=data.db_secret,
    encryption_key_secret=data.encryption_key_secret,
    env=env,
)

app.synth()
