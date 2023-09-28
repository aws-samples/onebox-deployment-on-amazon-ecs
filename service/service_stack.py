# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from typing import Any

import aws_cdk as cdk
import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_ecr_assets as ecr_assets
import aws_cdk.aws_elasticloadbalancingv2 as elbv2
import cdk_nag
from constructs import Construct

from service.compute import Compute
from service.compute_deployment_monitoring import ComputeDeploymentMonitoring
from service.reverse_proxy import ReverseProxy


class ServiceStack(cdk.Stack):
    def __init__(self, scope: Construct, id_: str, **kwargs: Any) -> None:
        super().__init__(scope, id_, **kwargs)

        vpc = ec2.Vpc(self, "Vpc")
        reverse_proxy = ReverseProxy(self, "ReverseProxy", vpc=vpc)
        compute = Compute(
            self,
            "Compute",
            vpc=vpc,
            reverse_proxy=reverse_proxy,
        )
        ComputeDeploymentMonitoring(
            self,
            "OneboxComputeDeploymentMonitoring",
            target_group=reverse_proxy.onebox_target_group,
            target_service=compute.onebox_service,
        )
        ComputeDeploymentMonitoring(
            self,
            "FleetComputeDeploymentMonitoring",
            target_group=reverse_proxy.fleet_target_group,
            target_service=compute.fleet_service,
        )

        # The following statements define class members used for creating public class properties
        self._ecs_cluster_name = compute.ecs_cluster_name
        self._onebox_service_name = compute.onebox_service_name
        self._fleet_service_name = compute.fleet_service_name

        self._create_outputs(reverse_proxy.alb, compute.runtime_container_image_asset)
        self._add_cdk_nag_suppressions(vpc, reverse_proxy.alb, compute)

    def _create_outputs(
        self,
        alb: elbv2.ApplicationLoadBalancer,
        runtime_container: ecr_assets.DockerImageAsset,
    ) -> None:
        self._web_api_endpoint = cdk.CfnOutput(
            self,
            id="WebAPIEndpoint",
            value=alb.load_balancer_dns_name,
        )

        self._runtime_container_image_url = cdk.CfnOutput(
            self,
            id="RuntimeContainerImageUrl",
            value=runtime_container.image_uri,
        )

    @property
    def web_api_endpoint(self) -> cdk.CfnOutput:
        return self._web_api_endpoint

    @property
    def runtime_container_image_url(self) -> cdk.CfnOutput:
        return self._runtime_container_image_url

    @property
    def ecs_cluster_name(self) -> str:
        return self._ecs_cluster_name

    @property
    def onebox_service_name(self) -> str:
        return self._onebox_service_name

    @property
    def fleet_service_name(self) -> str:
        return self._fleet_service_name

    @staticmethod
    def _add_cdk_nag_suppressions(
        vpc: ec2.Vpc, alb: elbv2.ApplicationLoadBalancer, compute: Compute
    ) -> None:
        # --- VPC ---
        vpc_flow_logs_suppression = cdk_nag.NagPackSuppression(
            id="AwsSolutions-VPC7",
            reason="Reduce costs for demo by disabling VPC flow logs",
        )
        cdk_nag.NagSuppressions.add_resource_suppressions(
            vpc, [vpc_flow_logs_suppression]
        )

        # -- Reverse Proxy ---
        elb_access_logs_suppression = cdk_nag.NagPackSuppression(
            id="AwsSolutions-ELB2",
            reason="Reduce costs for demo by disabling ELB access logs",
        )
        cdk_nag.NagSuppressions.add_resource_suppressions(
            alb, [elb_access_logs_suppression]
        )

        elb_security_group_suppression = cdk_nag.NagPackSuppression(
            id="AwsSolutions-EC23",
            reason="Allow incoming traffic from 0.0.0.0/0 to the ELB",
        )
        # `apply_to_children=True` because ALB construct API does not expose its security group
        cdk_nag.NagSuppressions.add_resource_suppressions(
            alb, [elb_security_group_suppression], apply_to_children=True
        )

        # --- ECS tasks execution role ---
        # TODO: Discuss further about Role vs IRole and possibly use casting
        aws_managed_policy_suppression = cdk_nag.NagPackSuppression(
            id="AwsSolutions-IAM4",
            reason="Simplifying IAM policy creation by allowing AWS managed policies",
        )
        cdk_nag.NagSuppressions.add_resource_suppressions(
            compute.task_execution_role,
            [aws_managed_policy_suppression],
        )
