# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import aws_cdk.aws_ecs as ecs
import aws_cdk.aws_elasticloadbalancingv2 as elbv2
from constructs import Construct

import constants


class ComputeDeploymentMonitoring(Construct):
    def __init__(
        self,
        scope: Construct,
        id_: str,
        target_group: elbv2.ApplicationTargetGroup,
        target_service: ecs.BaseService,
    ) -> None:
        super().__init__(scope, id_)

        target_response_time_alarm_parameters = (
            constants.ServiceConstants.TARGET_RESPONSE_TIME_METRIC_ALARM_PARAMETERS
        )

        target_response_time_metric = target_group.metric(
            metric_name=target_response_time_alarm_parameters.metric_name,
            statistic=target_response_time_alarm_parameters.statistic,
            period=target_response_time_alarm_parameters.period,
        )

        target_response_time_alarm = target_response_time_metric.create_alarm(
            self,
            f"{target_response_time_alarm_parameters.metric_name}-Alarm",
            threshold=target_response_time_alarm_parameters.threshold,
            evaluation_periods=target_response_time_alarm_parameters.evaluation_period,
            datapoints_to_alarm=target_response_time_alarm_parameters.datapoints_to_alarm,
        )

        target_service.enable_deployment_alarms(
            [target_response_time_alarm.alarm_name],
            behavior=ecs.AlarmBehavior.ROLLBACK_ON_ALARM,
        )
