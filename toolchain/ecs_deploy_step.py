# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import aws_cdk as cdk
import aws_cdk.aws_codepipeline as codepipeline
import aws_cdk.aws_codepipeline_actions as codepipeline_actions
import aws_cdk.aws_ecs as ecs
import jsii


@jsii.implements(cdk.pipelines.ICodePipelineActionFactory)
class EcsDeployStep(cdk.pipelines.Step):
    def __init__(
        self, id_: str, input_: cdk.pipelines.FileSet, ecs_service: ecs.IBaseService
    ) -> None:
        super().__init__(id_)

        self.input = input_
        self.ecs_service = ecs_service

        self.add_step_dependency(self.input.producer)

    @jsii.member(jsii_name="produceAction")
    def produce_action(
        self, stage: codepipeline.IStage, options: cdk.pipelines.ProduceActionOptions
    ) -> cdk.pipelines.CodePipelineActionFactoryResult:
        artifact = options.artifacts.to_code_pipeline(self.input)

        ecs_deploy_action = codepipeline_actions.EcsDeployAction(
            action_name=self.id,
            service=self.ecs_service,
            input=artifact,
            run_order=options.run_order,
        )

        stage.add_action(action=ecs_deploy_action)

        return cdk.pipelines.CodePipelineActionFactoryResult(run_orders_consumed=1)
