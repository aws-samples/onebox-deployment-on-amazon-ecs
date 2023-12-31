# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import aws_cdk as cdk
import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_elasticloadbalancingv2 as elbv2
import cdk_nag
from constructs import Construct

import constants


class ReverseProxy(Construct):
    def __init__(self, scope: Construct, id_: str, vpc: ec2.Vpc) -> None:
        super().__init__(scope, id_)

        self.onebox_target_group = self._create_target_group(
            vpc=vpc,
            deployment_stage=constants.DeploymentStage.ONEBOX,
            lb_health_check_path=constants.ServiceConstants.LB_HEALTH_CHECK_PATH,
            lb_health_check_timeout=constants.ServiceConstants.LB_HEALTH_CHECK_TIMEOUT,
        )
        self.fleet_target_group = self._create_target_group(
            vpc=vpc,
            deployment_stage=constants.DeploymentStage.FLEET,
            lb_health_check_path=constants.ServiceConstants.LB_HEALTH_CHECK_PATH,
            lb_health_check_timeout=constants.ServiceConstants.LB_HEALTH_CHECK_TIMEOUT,
        )
        self.alb = self._create_alb(vpc)

    def _create_target_group(
        self,
        vpc: ec2.Vpc,
        deployment_stage: str,
        lb_health_check_path: str,
        lb_health_check_timeout: cdk.Duration,
    ) -> elbv2.ApplicationTargetGroup:
        target_group = elbv2.ApplicationTargetGroup(
            self,
            f"{deployment_stage}TargetGroup",
            protocol=elbv2.ApplicationProtocol.HTTP,
            vpc=vpc,
        )

        target_group.configure_health_check(
            path=lb_health_check_path,
            timeout=lb_health_check_timeout,
        )

        return target_group

    def _create_alb(self, vpc: ec2.Vpc) -> elbv2.ApplicationLoadBalancer:
        alb = elbv2.ApplicationLoadBalancer(self, "ALB", vpc=vpc, internet_facing=True)
        weighted_forward_action = self._create_weighted_forward_action(
            onebox_target_group=self.onebox_target_group,
            onebox_weight=constants.ServiceConstants.ONEBOX_WEIGHT,
            fleet_target_group=self.fleet_target_group,
            fleet_weight=constants.ServiceConstants.FLEET_WEIGHT,
        )
        alb.add_listener(
            "Listener",
            default_action=weighted_forward_action,
            protocol=elbv2.ApplicationProtocol.HTTP,
        )
        self._add_alb_cdk_nag_suppression(alb)
        return alb

    @staticmethod
    def _create_weighted_forward_action(
        onebox_target_group: elbv2.ApplicationTargetGroup,
        onebox_weight: int,
        fleet_target_group: elbv2.ApplicationTargetGroup,
        fleet_weight: int,
    ) -> elbv2.ListenerAction:
        onebox_weighted_target_group = elbv2.WeightedTargetGroup(
            target_group=onebox_target_group,
            weight=onebox_weight,
        )
        fleet_weighted_target_group = elbv2.WeightedTargetGroup(
            target_group=fleet_target_group,
            weight=fleet_weight,
        )
        weighted_forward_action = elbv2.ListenerAction.weighted_forward(
            target_groups=[onebox_weighted_target_group, fleet_weighted_target_group],
        )
        return weighted_forward_action

    @staticmethod
    def _add_alb_cdk_nag_suppression(alb: elbv2.ApplicationLoadBalancer) -> None:
        elb_access_logs_suppression = cdk_nag.NagPackSuppression(
            id="AwsSolutions-ELB2",
            reason="ELB access logs are not needed for this CI/CD deployment strategy demo",
        )
        cdk_nag.NagSuppressions.add_resource_suppressions(
            alb, [elb_access_logs_suppression]
        )

        elb_security_group_suppression = cdk_nag.NagPackSuppression(
            id="AwsSolutions-EC23",
            reason="This ELB is internet facing and should be able to get traffic from 0.0.0.0/0",
        )
        cdk_nag.NagSuppressions.add_resource_suppressions(
            alb, [elb_security_group_suppression], apply_to_children=True
        )
