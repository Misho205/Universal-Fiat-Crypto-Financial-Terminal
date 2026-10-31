import { Module } from "@nestjs/common";
import { InstructionsController } from "../instructions.controller";

@Module({ controllers: [InstructionsController] })
export class InstructionsModule {}
