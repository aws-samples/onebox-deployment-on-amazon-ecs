# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import pathlib
from dataclasses import dataclass

import aws_cdk as cdk
import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_ecr_assets as ecr_assets
import aws_cdk.aws_ecs as ecs
import aws_cdk.aws_elasticloadbalancingv2 as elbv2
import aws_cdk.aws_iam as iam
import cdk_nag
from constructs import Construct

import constants
from service.reverse_proxy import ReverseProxy

RUNTIME_DIRECTORY_RELATIVE_PATH = "web_api"


@dataclass
class EcsServiceParameters:
    name: str
    task_definition: ecs.TaskDefinition
    autoscaling_parameters: constants.AutoscalingParameters


@dataclass
class ContainerParameters:
    image: ecs.ContainerImage
    name: str
    cpu: int
    memory: int
    port: int


class Compute(Construct):
    def __init__(
        self,
        scope: Construct,
        id_: str,
        vpc: ec2.Vpc,
        reverse_proxy: ReverseProxy,
    ) -> None:
        super().__init__(scope, id_)

        # --- ECS Cluster ---
        self._ecs_cluster_name = self._generate_ecs_cluster_name()
        ecs_cluster = self._create_ecs_cluster(vpc, self.ecs_cluster_name)

        # --- ECS Task Definition ---
        task_container_image = self._get_task_container_image()
        container_parameters = ContainerParameters(
            image=task_container_image,
            name=constants.ServiceConstants.APP_NAME,
            cpu=constants.ServiceConstants.CPU,
            memory=constants.ServiceConstants.MEMORY,
            port=constants.ServiceConstants.PORT,
        )
        task_definition = self._create_task_definition(
            container_parameters=container_parameters,
        )

        # --- ECS Services ---
        self._onebox_service_name = self._generate_ecs_service_name(
            stage=constants.DeploymentStage.ONEBOX,
        )
        onebox_ecs_service_parameters = EcsServiceParameters(
            name=self.onebox_service_name,
            task_definition=task_definition,
            autoscaling_parameters=constants.ServiceConstants.ONEBOX_AUTOSCALING_PARAMETERS,
        )
        self.onebox_service = self._create_and_configure_ecs_service(
            ecs_cluster=ecs_cluster,
            target_group=reverse_proxy.onebox_target_group,
            alb=reverse_proxy.alb,
            ecs_service_parameters=onebox_ecs_service_parameters,
        )

        self._fleet_service_name = self._generate_ecs_service_name(
            stage=constants.DeploymentStage.FLEET
        )
        fleet_ecs_service_parameters = EcsServiceParameters(
            name=self.fleet_service_name,
            task_definition=task_definition,
            autoscaling_parameters=constants.ServiceConstants.FLEET_AUTOSCALING_PARAMETERS,
        )
        self.fleet_service = self._create_and_configure_ecs_service(
            ecs_cluster=ecs_cluster,
            target_group=reverse_proxy.fleet_target_group,
            alb=reverse_proxy.alb,
            ecs_service_parameters=fleet_ecs_service_parameters,
        )

        # --- Runtime Assets ---
        self.runtime_container_image_asset = (
            self._create_runtime_container_image_asset()
        )

    def _generate_ecs_cluster_name(self) -> str:
        deployment_environment_name = cdk.Stack.of(self).stack_name.split("-")[-1]

        return constants.ServiceConstants.ECS_CLUSTER_NAME_TEMPLATE.format(
            app=constants.ServiceConstants.APP_NAME, env=deployment_environment_name
        )

    def _create_ecs_cluster(self, vpc: ec2.Vpc, cluster_name: str) -> ecs.Cluster:
        cluster = ecs.Cluster(
            self,
            "EcsCluster",
            vpc=vpc,
            enable_fargate_capacity_providers=True,
            cluster_name=cluster_name,
            container_insights=True,
        )
        return cluster

    def _get_task_container_image(self) -> ecs.ContainerImage:
        if (
            constants.DeploymentEnvironment.PROD.lower()
            in cdk.Stack.of(self).stack_name.lower()
        ):
            return self._create_bootstrap_container_image()
        return self._create_runtime_container_image()

    def _create_runtime_container_image(self) -> ecs.ContainerImage:
        directory_path = self._get_runtime_directory_path()
        container_image = ecs.ContainerImage.from_asset(directory=directory_path)
        return container_image

    def _create_runtime_container_image_asset(self) -> ecr_assets.DockerImageAsset:
        directory_path = self._get_runtime_directory_path()
        container_image = ecr_assets.DockerImageAsset(
            self, "RuntimeContainerImageAsset", directory=directory_path
        )
        return container_image

    def _create_task_definition(
        self, container_parameters: ContainerParameters
    ) -> ecs.TaskDefinition:
        execution_role = self._create_task_definition_execution_role()

        task_definition = ecs.FargateTaskDefinition(
            self,
            "TaskDefinition",
            memory_limit_mib=container_parameters.memory,
            cpu=container_parameters.cpu,
            execution_role=execution_role,
        )

        self._add_container_to_task_definition(
            task_definition=task_definition,
            container_parameters=container_parameters,
        )
        return task_definition

    def _create_task_definition_execution_role(self) -> iam.IRole:
        execution_role = iam.Role(
            self,
            "TaskDefinitionExecutionRole",
            assumed_by=iam.ServicePrincipal(service="ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                )
            ],
        )

        self._add_cdk_nag_ecs_execution_role_suppression(execution_role)
        return execution_role.without_policy_updates()

    @property
    def ecs_cluster_name(self) -> str:
        return self._ecs_cluster_name

    @property
    def onebox_service_name(self) -> str:
        return self._onebox_service_name

    @property
    def fleet_service_name(self) -> str:
        return self._fleet_service_name

    def _create_and_configure_ecs_service(
        self,
        ecs_cluster: ecs.Cluster,
        alb: elbv2.ApplicationLoadBalancer,
        target_group: elbv2.ApplicationTargetGroup,
        ecs_service_parameters: EcsServiceParameters,
    ) -> ecs.FargateService:
        ecs_service = self._create_autoscaled_fargate_service(
            cluster=ecs_cluster,
            ecs_service_parameters=ecs_service_parameters,
        )

        target_group.add_target(ecs_service)
        ecs_service.connections.allow_from(
            alb, ec2.Port.tcp(constants.ServiceConstants.PORT)
        )

        return ecs_service

    def _create_autoscaled_fargate_service(
        self,
        cluster: ecs.Cluster,
        ecs_service_parameters: EcsServiceParameters,
    ) -> ecs.FargateService:
        fargate_service = ecs.FargateService(
            self,
            f"EcsService-{ecs_service_parameters.name}",
            service_name=ecs_service_parameters.name,
            task_definition=ecs_service_parameters.task_definition,
            cluster=cluster,
            desired_count=ecs_service_parameters.autoscaling_parameters.desired_capacity,
        )

        self._configure_service_autoscaling(
            service=fargate_service,
            autoscaling_parameters=ecs_service_parameters.autoscaling_parameters,
        )

        return fargate_service

    @staticmethod
    def _add_cdk_nag_ecs_execution_role_suppression(execution_role: iam.Role) -> None:
        aws_managed_policy_suppression = cdk_nag.NagPackSuppression(
            id="AwsSolutions-IAM4",
            reason="Allow the usage of AWS managed policies in this CI/CD deployment strategy demo",
        )
        cdk_nag.NagSuppressions.add_resource_suppressions(
            execution_role, [aws_managed_policy_suppression]
        )

    @staticmethod
    def _get_runtime_directory_path() -> str:
        return str(
            pathlib.Path(__file__)
            .parent.joinpath(RUNTIME_DIRECTORY_RELATIVE_PATH)
            .resolve()
        )

    @staticmethod
    def _generate_ecs_service_name(stage: str) -> str:
        return constants.ServiceConstants.ECS_SERVICE_NAME_TEMPLATE.format(
            app=constants.ServiceConstants.APP_NAME, stage=stage
        )

    @staticmethod
    def _create_bootstrap_container_image() -> ecs.ContainerImage:
        container_image = ecs.ContainerImage.from_registry(
            name=constants.ServiceConstants.BOOTSTRAP_CONTAINER_IMAGE,
        )
        return container_image

    @staticmethod
    def _add_container_to_task_definition(
        task_definition: ecs.FargateTaskDefinition,
        container_parameters: ContainerParameters,
    ) -> ecs.ContainerDefinition:
        container = task_definition.add_container(
            f"Container{container_parameters.name}",
            container_name=container_parameters.name,
            image=container_parameters.image,
            cpu=container_parameters.cpu,
            memory_limit_mib=container_parameters.memory,
            logging=ecs.LogDriver.aws_logs(stream_prefix=container_parameters.name),
        )

        http_port_mapping = ecs.PortMapping(container_port=container_parameters.port)
        container.add_port_mappings(http_port_mapping)

        return container

    @staticmethod
    def _configure_service_autoscaling(
        service: ecs.FargateService,
        autoscaling_parameters: constants.AutoscalingParameters,
    ) -> None:
        autoscaling = service.auto_scale_task_count(
            min_capacity=autoscaling_parameters.min_capacity,
            max_capacity=autoscaling_parameters.max_capacity,
        )
        autoscaling.scale_on_cpu_utilization(
            "CpuScaling",
            target_utilization_percent=autoscaling_parameters.target_cpu_utilization,
        )
