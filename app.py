#!/usr/bin/env python3

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import aws_cdk as cdk
import cdk_nag

import constants
from service.service_stack import ServiceStack
from toolchain.toolchain_stack import ToolchainStack

app = cdk.App()

ServiceStack(
    app,
    f"{constants.Service.APP_NAME}-Service-Sandbox",
    env=constants.SANDBOX_ENVIRONMENT,
)

ToolchainStack(
    app,
    f"{constants.Service.APP_NAME}-Toolchain-Deployments",
    env=constants.DEPLOYMENTS_ENVIRONMENT,
)

cdk.Aspects.of(app).add(cdk_nag.AwsSolutionsChecks())
app.synth()
