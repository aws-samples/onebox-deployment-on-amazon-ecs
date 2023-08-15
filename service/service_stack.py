# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from typing import Any

import aws_cdk as cdk
import aws_cdk.aws_ec2 as ec2
import cdk_nag
from constructs import Construct

from service.compute import Compute
from service.compute_deployment_monitoring import ComputeDeploymentMonitoring
from service.reverse_proxy import ReverseProxy


class ServiceStack(cdk.Stack):
    def __init__(self, scope: Construct, id_: str, **kwargs: Any) -> None:
        super().__init__(scope, id_, **kwargs)

        vpc = self._create_vpc()
        reverse_proxy = ReverseProxy(self, "ReverseProxy", vpc=vpc)
        self.compute = Compute(
            self,
            "Compute",
            vpc=vpc,
            reverse_proxy=reverse_proxy,
        )
        ComputeDeploymentMonitoring(
            self,
            "OneboxComputeDeploymentMonitoring",
            target_group=reverse_proxy.onebox_target_group,
            target_service=self.compute.onebox_service,
        )
        ComputeDeploymentMonitoring(
            self,
            "FleetComputeDeploymentMonitoring",
            target_group=reverse_proxy.fleet_target_group,
            target_service=self.compute.fleet_service,
        )

        self._create_outputs(reverse_proxy)

    def _create_vpc(self) -> ec2.Vpc:
        vpc = ec2.Vpc(self, "Vpc")
        self._add_vpc_cdk_nag_suppression(vpc)
        return vpc

    def _create_outputs(self, reverse_proxy: ReverseProxy) -> None:
        self._web_api_endpoint = cdk.CfnOutput(
            self,
            id="WebAPIEndpoint",
            value=reverse_proxy.alb.load_balancer_dns_name,
        )

        self._runtime_container_image_url = cdk.CfnOutput(
            self,
            id="RuntimeContainerImageUrl",
            value=self.compute.runtime_container_image_asset.image_uri,
        )

    @property
    def web_api_endpoint(self) -> cdk.CfnOutput:
        return self._web_api_endpoint

    @property
    def runtime_container_image_url(self) -> cdk.CfnOutput:
        return self._runtime_container_image_url

    @staticmethod
    def _add_vpc_cdk_nag_suppression(vpc: ec2.Vpc) -> None:
        vpc_flow_logs_suppression = cdk_nag.NagPackSuppression(
            id="AwsSolutions-VPC7",
            reason="VPC flow logs are not needed for this CI/CD deployment strategy demo",
        )
        cdk_nag.NagSuppressions.add_resource_suppressions(
            vpc, [vpc_flow_logs_suppression]
        )
