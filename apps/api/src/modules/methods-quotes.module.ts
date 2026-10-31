import { Module } from "@nestjs/common";
import { MethodsQuotesController } from "../methods.controller";

@Module({ controllers: [MethodsQuotesController] })
export class MethodsQuotesModule {}
