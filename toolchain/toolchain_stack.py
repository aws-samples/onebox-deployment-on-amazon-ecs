# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from typing import Any

import aws_cdk as cdk
import aws_cdk.aws_codecommit as codecommit
import aws_cdk.aws_ecs as ecs
import aws_cdk.aws_iam as iam
import cdk_nag
from constructs import Construct

import constants
from service.service_stack import ServiceStack
from toolchain.ecs_deploy_step import EcsDeployStep


class ToolchainStack(cdk.Stack):
    def __init__(self, scope: Construct, id_: str, **kwargs: Any) -> None:
        super().__init__(scope, id_, **kwargs)

        repository = codecommit.Repository.from_repository_name(
            self,
            "CodeCommitRepository",
            repository_name=constants.ServiceConstants.APP_NAME.lower(),
        )
        pipeline = self._create_base_cdk_pipeline(repository)
        # Include pre-production environments here, e.g., Alpha, Beta, Gamma
        self._add_prod_stage_to_pipeline(pipeline)

        self._add_pipeline_cdk_nag_suppression(pipeline)

    def _create_base_cdk_pipeline(
        self,
        repository: codecommit.IRepository,
    ) -> cdk.pipelines.CodePipeline:
        pipeline_source = cdk.pipelines.CodePipelineSource.code_commit(
            repository=repository,
            branch=constants.ServiceConstants.APP_REPOSITORY_BRANCH,
        )

        allow_assume_bootstrap_lookup_role = iam.PolicyStatement(
            actions=["sts:AssumeRole"],
            resources=["*"],
            effect=iam.Effect.ALLOW,
            conditions={
                "StringEquals": {"iam:ResourceTag/aws-cdk:bootstrap-role": "lookup"}
            },
        )

        synth_step = cdk.pipelines.CodeBuildStep(
            "SynthStep",
            input=pipeline_source,
            install_commands=["npm i -g npm@latest"],
            commands=[
                "./scripts/install-deps.sh",
                "npx cdk synth",
            ],
            role_policy_statements=[allow_assume_bootstrap_lookup_role],
        )

        pipeline = cdk.pipelines.CodePipeline(
            self,
            "Pipeline",
            synth=synth_step,
            docker_enabled_for_synth=True,
        )

        return pipeline

    def _add_prod_stage_to_pipeline(self, pipeline: cdk.pipelines.CodePipeline) -> None:
        prod_stage = cdk.Stage(
            pipeline,
            "Prod",
            env=constants.PRODUCTION_ENVIRONMENT,
        )

        prod_service_stack = ServiceStack(
            prod_stage,
            f"{constants.ServiceConstants.APP_NAME}-Service-Prod",
            stack_name=f"{constants.ServiceConstants.APP_NAME}-Service-Prod",
        )

        prod_stage_deployment = pipeline.add_stage(prod_stage)

        # Create Onebox/Fleet deployment steps
        image_definitions_generation_step = (
            self._create_image_definition_generation_step(prod_service_stack)
        )

        if image_definitions_generation_step.primary_output is None:
            raise ValueError(
                "image_definitions_generation_step.primary_output should never be None"
            )

        cluster_name = prod_service_stack.compute.ecs_cluster_name
        onebox_service_name = prod_service_stack.compute.onebox_service_name
        fleet_service_name = prod_service_stack.compute.fleet_service_name

        onebox_deployment_step = self._create_ecs_deployment_step(
            account=prod_service_stack.account,
            region=prod_service_stack.region,
            cluster_name=cluster_name,
            service_name=onebox_service_name,
            image_definitions_artifact=image_definitions_generation_step.primary_output,
            deployment_stage=constants.DeploymentStage.ONEBOX,
        )

        fleet_deployment_step = self._create_ecs_deployment_step(
            account=prod_service_stack.account,
            region=prod_service_stack.region,
            cluster_name=cluster_name,
            service_name=fleet_service_name,
            image_definitions_artifact=image_definitions_generation_step.primary_output,
            deployment_stage=constants.DeploymentStage.FLEET,
        )

        # Create dependencies to create wanted pipeline flow:
        # Image Definition Generation -> Onebox -> Fleet
        onebox_deployment_step.add_step_dependency(image_definitions_generation_step)
        fleet_deployment_step.add_step_dependency(onebox_deployment_step)

        prod_stage_deployment.add_post(image_definitions_generation_step)
        prod_stage_deployment.add_post(onebox_deployment_step)
        prod_stage_deployment.add_post(fleet_deployment_step)

    # pylint: disable=R0913
    def _create_ecs_deployment_step(
        self,
        image_definitions_artifact: cdk.pipelines.FileSet,
        cluster_name: str,
        service_name: str,
        deployment_stage: str,
        account: str,
        region: str,
    ) -> EcsDeployStep:
        ecs_service = self._import_ecs_service(
            account=account,
            region=region,
            cluster_name=cluster_name,
            service_name=service_name,
        )

        ecs_deploy_step = EcsDeployStep(
            id_=f"EcsDeploy{deployment_stage}",
            input_=image_definitions_artifact,
            ecs_service=ecs_service,
        )

        return ecs_deploy_step

    def _import_ecs_service(
        self, region: str, account: str, cluster_name: str, service_name: str
    ) -> ecs.IBaseService:
        service_arn = cdk.Arn.format(
            components=cdk.ArnComponents(
                arn_format=cdk.ArnFormat.SLASH_RESOURCE_NAME,
                partition="aws",
                service="ecs",
                region=region,
                account=account,
                resource="service",
                resource_name=f"{cluster_name}/{service_name}",
            )
        )

        # The scope for the imported service is the Toolchain stack
        ecs_service = ecs.FargateService.from_service_arn_with_cluster(
            self,
            service_name,
            service_arn=service_arn,
        )

        return ecs_service

    @staticmethod
    def _create_image_definition_generation_step(
        service_stack: ServiceStack,
    ) -> cdk.pipelines.ShellStep:
        image_name_env_var_name = "IMAGE_NAME"
        image_uri_env_var_name = "IMAGE_URI"
        image_definitions_file_name = "imagedefinitions.json"
        primary_output_directory = "ecs_deployment"
        create_output_directory_command = f"mkdir {primary_output_directory}"
        create_image_definitions_command = f"""
            jq -n \\
                --arg name ${image_name_env_var_name} \\
                --arg uri ${image_uri_env_var_name} \\
                \'[{{name: $name, imageUri: $uri}}]\' > {primary_output_directory}/{image_definitions_file_name}
        """

        image_definitions_creation_step = cdk.pipelines.ShellStep(
            "GenerateImageDefinitionJson",
            commands=[
                create_output_directory_command,
                create_image_definitions_command,
            ],
            env={image_name_env_var_name: constants.ServiceConstants.APP_NAME},
            env_from_cfn_outputs={
                image_uri_env_var_name: service_stack.runtime_container_image_url
            },
            primary_output_directory=primary_output_directory,
        )

        return image_definitions_creation_step

    @staticmethod
    def _add_pipeline_cdk_nag_suppression(pipeline: cdk.pipelines.CodePipeline) -> None:
        # Force the pipeline construct creation forward before applying suppressions.
        # See https://github.com/aws/aws-cdk/issues/18440
        pipeline.build_pipeline()

        wildcard_permissions_suppression = cdk_nag.NagPackSuppression(
            id="AwsSolutions-IAM5",
            reason="We have no control over the IAM permissions created by CDK Pipelines",
        )
        kms_encrypted_codebuild_project_suppression = cdk_nag.NagPackSuppression(
            id="AwsSolutions-CB4",
            reason="We have no control over the CodeBuild projects created by CDK Pipelines",
        )
        s3_server_access_logs_suppression = cdk_nag.NagPackSuppression(
            id="AwsSolutions-S1",
            reason="We have no control over the Artifacts S3 bucket created by CDK Pipelines",
        )
        privileged_codebuild_project_logs_suppression = cdk_nag.NagPackSuppression(
            id="AwsSolutions-CB3",
            reason="We have no control over the CodeBuild projects created by CDK Pipelines",
        )
        cdk_nag.NagSuppressions.add_resource_suppressions(
            pipeline,
            [
                wildcard_permissions_suppression,
                kms_encrypted_codebuild_project_suppression,
                s3_server_access_logs_suppression,
                privileged_codebuild_project_logs_suppression,
            ],
            apply_to_children=True,
        )
