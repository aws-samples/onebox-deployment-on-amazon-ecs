# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
from dataclasses import dataclass

import aws_cdk as cdk
from aws_cdk import aws_cloudwatch as cloudwatch

# The current values for all environments are for demonstration only, please
# consider replacing them with your own account-ids and region before deploying.
SANDBOX_ENVIRONMENT = cdk.Environment(
    account=os.environ["CDK_DEFAULT_ACCOUNT"],
    region=os.environ["CDK_DEFAULT_REGION"],
)

DEPLOYMENTS_ENVIRONMENT = cdk.Environment(
    account=os.environ["CDK_DEFAULT_ACCOUNT"],
    region=os.environ["CDK_DEFAULT_REGION"],
)

PRODUCTION_ENVIRONMENT = cdk.Environment(
    account=os.environ["CDK_DEFAULT_ACCOUNT"],
    region=os.environ["CDK_DEFAULT_REGION"],
)


# pylint: disable=R0903
class DeploymentEnvironment:
    SANDBOX = "Sandbox"
    PROD = "Prod"


# pylint: disable=R0903
class DeploymentStage:
    ONEBOX = "Onebox"
    FLEET = "Fleet"


@dataclass
class AutoscalingParameters:
    deployment_stage: str
    min_capacity: int
    desired_capacity: int
    max_capacity: int
    target_cpu_utilization: int


@dataclass
class MetricAlarmParameters:
    metric_name: str
    statistic: str
    period: cdk.Duration
    threshold: int
    evaluation_period: int
    datapoints_to_alarm: int


# pylint: disable=R0903
class Service:
    APP_NAME = "OneBoxDeploymentOnECS"
    APP_REPOSITORY_BRANCH = "main"

    ECS_CLUSTER_NAME_TEMPLATE = "{app}-{env}"
    ECS_SERVICE_NAME_TEMPLATE = "{app}-{stage}"

    PORT = 80
    CPU = 512
    MEMORY = 2048
    LOG_PREFIX = APP_NAME

    ONEBOX_WEIGHT = 1
    FLEET_WEIGHT = 99

    # DO NOT CHANGE (UNLESS YOU KNOW WHAT YOU ARE DOING)
    # Changing this cause clean-deployment for the application, deploying {BASE_IMAGE_NAME}
    # to both onebox and fleet services at the same time before deploying the application image
    BOOTSTRAP_CONTAINER_IMAGE = "nginx:1.23.3"

    LB_HEALTH_CHECK_PATH = "/"
    LB_HEALTH_CHECK_TIMEOUT = cdk.Duration.seconds(10)

    TARGET_RESPONSE_TIME_METRIC_ALARM_PARAMETERS = MetricAlarmParameters(
        metric_name="TargetResponseTime",
        statistic=cloudwatch.Stats.trimmed_mean(90, 100),
        period=cdk.Duration.minutes(1),
        threshold=3,
        evaluation_period=4,
        datapoints_to_alarm=3,
    )

    ONEBOX_AUTOSCALING_PARAMETERS = AutoscalingParameters(
        deployment_stage=DeploymentStage.ONEBOX,
        min_capacity=3,
        desired_capacity=3,
        max_capacity=10,
        target_cpu_utilization=75,
    )

    FLEET_AUTOSCALING_PARAMETERS = AutoscalingParameters(
        deployment_stage=DeploymentStage.FLEET,
        min_capacity=10,
        desired_capacity=10,
        max_capacity=1000,
        target_cpu_utilization=75,
    )
